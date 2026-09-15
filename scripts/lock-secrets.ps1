# Restringe en disco los archivos que contienen credenciales o datos personales.
#
# Por defecto, todo lo que vive bajo el perfil del usuario hereda permisos que
# incluyen a otros principales del sistema. Estos archivos no deberian: el .env
# tiene claves de API activas y el JWT_SECRET, backups/ tiene hashes de
# contrasena y refresh tokens, y backend/secrets/ tiene la credencial de admin
# de Firebase.
#
# Lo que hace: corta la herencia y deja acceso solo al usuario actual y a
# SYSTEM (que lo necesita para respaldos e indexado del propio Windows).
#
# Es idempotente y reversible:
#   icacls <ruta> /reset /T
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\lock-secrets.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\lock-secrets.ps1 -Verify

param([switch]$Verify)

$ErrorActionPreference = "Stop"
$repoDir = Split-Path -Parent $PSScriptRoot
$me = "$env:USERDOMAIN\$env:USERNAME"

$targets = @(
    @{ Path = Join-Path $repoDir ".env";             Kind = "file" },
    @{ Path = Join-Path $repoDir "backups";          Kind = "dir"  },
    @{ Path = Join-Path $repoDir "backend\secrets";  Kind = "dir"  },
    @{ Path = Join-Path $repoDir "backend\runtime";  Kind = "dir"  }
)

foreach ($t in $targets) {
    if (-not (Test-Path $t.Path)) {
        Write-Host "[saltado] no existe: $($t.Path)"
        continue
    }

    if ($Verify) {
        $acl = (Get-Acl $t.Path).Access |
            Where-Object { -not $_.IsInherited } |
            ForEach-Object { $_.IdentityReference.Value } |
            Sort-Object -Unique
        $inherited = (Get-Acl $t.Path).Access | Where-Object { $_.IsInherited }
        $estado = if ($inherited) { "HEREDA (sin proteger)" } else { "protegido" }
        Write-Host "[$estado] $($t.Path)"
        Write-Host "    acceso: $($acl -join ', ')"
        continue
    }

    # /inheritance:r  -> corta la herencia y elimina las ACE heredadas
    # /grant:r        -> reemplaza (no acumula) los permisos de ese principal
    # (OI)(CI)        -> se propaga a archivos y subcarpetas (solo en carpetas)
    $flags = if ($t.Kind -eq "dir") { "(OI)(CI)F" } else { "F" }
    & icacls $t.Path /inheritance:r /grant:r "${me}:$flags" /grant:r "SYSTEM:$flags" /Q | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "icacls fallo en $($t.Path)"
        exit 1
    }
    Write-Host "[protegido] $($t.Path)"
}

if (-not $Verify) {
    Write-Host ""
    Write-Host "Listo. Verifica con:  .\scripts\lock-secrets.ps1 -Verify"
    Write-Host "Revertir con:         icacls <ruta> /reset /T"
}
