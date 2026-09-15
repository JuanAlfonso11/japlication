# Backs up the JobPilot Postgres database to scripts\..\backups\ as a
# timestamped .sql file, then deletes backups older than $RetentionDays.
# Run manually any time, or scheduled automatically (see
# install-backup-schedule.ps1, which runs this daily at 3 AM).

$ErrorActionPreference = "Stop"

$RetentionDays = 30

$repoDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "Send-Heartbeat.ps1")
$backupDir = Join-Path $repoDir "backups"
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backupFile = Join-Path $backupDir "jobflow_$timestamp.sql"

Set-Location $repoDir

Write-Host "[JobPilot backup] Dumping database..."

# pg_dump escribe DENTRO del contenedor y luego se copia el archivo tal cual.
#
# Antes esto era `docker compose exec ... > $backupFile`. En Windows
# PowerShell 5.1 -- que es con lo que corre la tarea programada -- el operador
# `>` es Out-File, y Out-File escribe en UTF-16LE. Los backups llevaban meses
# guardandose en UTF-16: BOM ff fe al principio y el doble de tamano (4.517.336
# bytes en disco para un dump de 2.420.790 caracteres). Restauraban solo si se
# pasaba por `Get-Content`, que detecta el BOM y decodifica -- que es justo lo
# que hace el simulacro documentado en scripts/README.md, por eso paso sin que
# nadie viera nada. Cualquier otra via (psql -f, otra maquina, otra
# herramienta) fallaba, y no se habria sabido hasta el dia de necesitarlo.
#
# `docker compose cp` copia bytes, sin capa de texto que pueda recodificar.
$innerFile = "/tmp/jobflow_$timestamp.sql"
docker compose exec -T db pg_dump -U jobflow -d jobflow --no-owner --no-privileges -f $innerFile
if ($LASTEXITCODE -eq 0) {
    docker compose cp "db:$innerFile" $backupFile
    docker compose exec -T db rm -f $innerFile | Out-Null
}

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $backupFile) -or (Get-Item $backupFile).Length -eq 0) {
    Send-Heartbeat -JobName "backup" -Status "error" -Detail "pg_dump failed or produced an empty file"
    Write-Error "[JobPilot backup] pg_dump failed or produced an empty file."
    if (Test-Path $backupFile) { Remove-Item $backupFile -Force }
    exit 1
}

# El fallo que hubo aqui era invisible: el archivo existia, no estaba vacio, y
# el chequeo de arriba pasaba. Esto mira los dos primeros bytes, que es donde
# se veia. Un dump de Postgres empieza siempre en ASCII ("--" de un comentario
# o "SET"), nunca con un BOM.
$firstBytes = [System.IO.File]::ReadAllBytes($backupFile)[0..1]
if ($firstBytes[0] -eq 0xFF -or $firstBytes[0] -eq 0xFE -or $firstBytes[1] -eq 0x00) {
    Send-Heartbeat -JobName "backup" -Status "error" -Detail "El backup salio con BOM o en UTF-16 - no restaurara"
    Write-Error "[JobPilot backup] El archivo empieza con un BOM o con un byte nulo: no es UTF-8."
    exit 1
}

$sizeKB = [math]::Round((Get-Item $backupFile).Length / 1KB, 1)
Send-Heartbeat -JobName "backup" -Status "ok" -Detail "$sizeKB KB"
Write-Host "[JobPilot backup] Saved $backupFile ($sizeKB KB)"

$cutoff = (Get-Date).AddDays(-$RetentionDays)
$old = Get-ChildItem $backupDir -Filter "jobflow_*.sql" | Where-Object { $_.LastWriteTime -lt $cutoff }
if ($old) {
    $old | Remove-Item -Force
    Write-Host "[JobPilot backup] Removed $($old.Count) backup(s) older than $RetentionDays days."
}

# Same retention window applied to error_logs. That table only ever grows,
# and while a handful of rows a week is nothing, one component crashing in a
# render loop can write a burst of them. Pruning here rather than in the API
# keeps the write path fast and puts all the housekeeping in the one job
# that already runs daily and already talks to the database.
#
# Deliberately after the dump above: a row is preserved in that night's
# backup before it's deleted here, so nothing is lost outright.
Write-Host "[JobPilot backup] Pruning error_logs older than $RetentionDays days..."
$ErrorActionPreference = "Continue"
docker compose exec -T db psql -U jobflow -d jobflow -c "DELETE FROM error_logs WHERE created_at < now() - interval '$RetentionDays days';" 2>&1 | ForEach-Object { Write-Host $_ }
$ErrorActionPreference = "Stop"
