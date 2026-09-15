# Comprueba que db/schema.sql y las migraciones de Alembic produzcan el MISMO esquema.
#
# Por que existe esto:
#   app/scripts/migrate.py trata a una base que tiene tablas pero no tiene
#   historial de Alembic como "nacio de schema.sql, ya esta al dia" y le hace
#   `alembic stamp head`. Esa suposicion es correcta SOLO si schema.sql esta
#   realmente sincronizado con las migraciones.
#
#   Cuando no lo esta, el fallo es silencioso y permanente: un volumen nuevo
#   (docker compose down -v, o restaurar en otra maquina) carga schema.sql,
#   se marca como al dia, y las columnas que solo existian en las migraciones
#   NO se aplican nunca. Ninguna migracion futura las va a arreglar, porque
#   para Alembic ya estan puestas.
#
#   Paso de verdad: las migraciones 0006 y 0007 (translations, language,
#   'linkedin') vivieron semanas fuera de schema.sql.
#
# Que hace: levanta dos bases desechables en el contenedor de Postgres, carga
# una con schema.sql y la otra con `alembic upgrade head`, y compara el dump
# de ambas. Es de solo lectura sobre la base real `jobflow`.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\check-schema-drift.ps1
# Codigo de salida 0 = sin deriva, 1 = hay deriva (o no se pudo comprobar).

# "Continue", no "Stop": docker, psql y alembic escriben avisos informativos
# (INFO, NOTICE) por stderr, y PowerShell convierte cada uno en un registro de
# error. Con "Stop" el script se moria en el primer INFO de Alembic sin llegar
# a comparar nada. Cada paso comprueba su $LASTEXITCODE explicitamente, que es
# la senal fiable con comandos nativos.
$ErrorActionPreference = "Continue"
$repoDir = Split-Path -Parent $PSScriptRoot
Set-Location $repoDir

$FROM_SQL = "drift_from_schema"
$FROM_MIG = "drift_from_migrations"

function Fail($msg) { Write-Host "[deriva] $msg" -ForegroundColor Red; exit 1 }

# --- el contenedor tiene que estar arriba ---
$dbUp = docker compose ps --status running --services 2>$null
if ($LASTEXITCODE -ne 0 -or $dbUp -notcontains "db") {
    Fail "el contenedor 'db' no esta corriendo. Arranca con: docker compose up -d db"
}

Write-Host "[deriva] creando bases desechables..."
foreach ($d in @($FROM_SQL, $FROM_MIG)) {
    docker compose exec -T db psql -U jobflow -d postgres -c "DROP DATABASE IF EXISTS $d" | Out-Null
    docker compose exec -T db psql -U jobflow -d postgres -c "CREATE DATABASE $d" | Out-Null
}

try {
    # --- 1. base construida desde schema.sql ---
    Write-Host "[deriva] cargando db/schema.sql..."
    Get-Content db\schema.sql -Raw | docker compose exec -T db psql -U jobflow -d $FROM_SQL -v ON_ERROR_STOP=1 -q
    if ($LASTEXITCODE -ne 0) { Fail "schema.sql no se pudo cargar sin errores" }

    # --- 2. base construida desde las migraciones ---
    Write-Host "[deriva] corriendo alembic upgrade head..."
    # `exec` sobre el backend que ya corre, no `run`: `run` levanta un
    # contenedor nuevo y, si docker-compose.yml cambio desde el ultimo `up`,
    # recrea tambien sus dependencias — es decir, reinicia la base de datos de
    # la app solo por comprobar el esquema.
    # La salida se guarda en una variable en vez de mandarla a Out-Null: los
    # INFO de Alembic salen por stderr y PowerShell los convierte en registros
    # de error, asi que hay que quedarse con el codigo de salida real y poder
    # imprimir el detalle si falla.
    $migOut = docker compose exec -T backend python -m app.scripts.migrate --database $FROM_MIG 2>&1
    if ($LASTEXITCODE -ne 0) {
        $migOut | Select-Object -Last 15 | ForEach-Object { Write-Host "    $_" }
        Fail "las migraciones fallaron sobre una base vacia"
    }

    # --- 3. comparar ---
    Write-Host "[deriva] comparando esquemas..."
    $tmp = [System.IO.Path]::GetTempPath()
    $a = Join-Path $tmp "drift_schema.txt"
    $b = Join-Path $tmp "drift_migrations.txt"

    # --schema-only, sin comentarios ni owners, y sin la tabla de control de
    # Alembic (que por definicion solo existe en una de las dos).
    $dumpArgs = "--schema-only --no-owner --no-privileges --no-comments -T alembic_version"
    docker compose exec -T db sh -c "pg_dump -U jobflow -d $FROM_SQL $dumpArgs" |
        Where-Object { $_ -notmatch '^\s*--' -and $_.Trim() -ne '' } | Sort-Object | Set-Content $a
    docker compose exec -T db sh -c "pg_dump -U jobflow -d $FROM_MIG $dumpArgs" |
        Where-Object { $_ -notmatch '^\s*--' -and $_.Trim() -ne '' } | Sort-Object | Set-Content $b

    $diff = Compare-Object (Get-Content $a) (Get-Content $b)
    if ($diff) {
        Write-Host ""
        Write-Host "DERIVA DETECTADA entre db/schema.sql y las migraciones:" -ForegroundColor Red
        Write-Host "  '<=' solo en schema.sql   '=>' solo en las migraciones" -ForegroundColor DarkGray
        Write-Host ""
        $diff | ForEach-Object {
            $side = if ($_.SideIndicator -eq "<=") { "solo-schema.sql " } else { "solo-migraciones" }
            Write-Host ("  [{0}] {1}" -f $side, $_.InputObject.Trim())
        }
        Write-Host ""
        Write-Host "Arreglalo poniendo el cambio en AMBOS archivos y vuelve a correr esto." -ForegroundColor Yellow
        exit 1
    }

    Write-Host ""
    Write-Host "[deriva] OK - schema.sql y las migraciones producen el mismo esquema." -ForegroundColor Green
    exit 0
}
finally {
    foreach ($d in @($FROM_SQL, $FROM_MIG)) {
        docker compose exec -T db psql -U jobflow -d postgres -c "DROP DATABASE IF EXISTS $d" 2>$null | Out-Null
    }
}
