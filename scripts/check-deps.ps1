# Busca vulnerabilidades conocidas en las dependencias de JobPilot, una vez
# por semana.
#
# Por que existe:
#   JobPilot es publico (tailscale funnel). En septiembre 2026 el frontend
#   seguia en Next 14 con una RCE sin login publicada hacia meses, y nadie se
#   entero hasta auditarlo a mano. Las vulnerabilidades aparecen sin que el
#   codigo cambie, asi que el pre-commit no basta: esto las busca solo.
#
# Frontend: npm audit (solo dependencias de runtime) en un contenedor de Node.
# Backend: pip-audit sobre la imagen cld-backend, que es lo que corre de verdad.
# Pytest se ignora: solo existe para los tests, nunca atiende una peticion.
#
# Reporta por heartbeat (job "deps_audit"), asi que el resultado aparece en
# Perfil -> Estado del sistema junto al resto.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\check-deps.ps1

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "Send-Heartbeat.ps1")

$repoDir = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $repoDir "frontend"
$problems = @()

# docker escribe progreso en stderr; se juzga solo por el codigo de salida.
$npm = docker run --rm -v "${frontend}\package.json:/app/package.json:ro" `
    -v "${frontend}\package-lock.json:/app/package-lock.json:ro" -w /app node:22-slim `
    npm audit --omit=dev --audit-level=high 2>&1
if ($LASTEXITCODE -ne 0) {
    $summary = ($npm | Select-String -Pattern "vulnerabilit" | Select-Object -Last 1)
    $problems += "frontend: $summary"
}

# --user root solo en este contenedor desechable: la imagen corre sin root y
# no podria instalar pip-audit.
$pip = docker run --rm --user root --entrypoint sh cld-backend -c `
    "pip install -q pip-audit >/dev/null 2>&1; pip-audit --progress-spinner off 2>/dev/null | awk 'NR>2 {print `$1}' | sort -u" 2>&1
$pipPkgs = @($pip | Where-Object { $_ -and $_.Trim() -and $_.Trim() -ne "pytest" })
if ($pipPkgs.Count -gt 0) {
    $problems += "backend: " + ($pipPkgs -join ", ")
}

if ($problems.Count -gt 0) {
    $detail = "Dependencias con vulnerabilidades conocidas -> " + ($problems -join " | ")
    Send-Heartbeat -JobName "deps_audit" -Status "error" -Detail $detail
    Write-Warning "[deps] $detail"
    exit 1
}

Send-Heartbeat -JobName "deps_audit" -Status "ok" -Detail "npm audit y pip-audit sin hallazgos"
Write-Host "[deps] OK - npm audit y pip-audit sin hallazgos"
exit 0
