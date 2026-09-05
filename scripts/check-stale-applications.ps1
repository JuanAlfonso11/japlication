# Runs the daily "did you follow up?" check for applications stuck in
# `applied` with no movement in a while (backend/app/scripts/
# check_stale_applications.py), straight inside the backend container.
# Separate from daily-job-sweep.ps1 (which runs every 2 hours) — this one
# only needs to run once a day, since re-checking staleness more often
# would just re-send the same reminder before its own re-notify window.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
Set-Location $repoDir
. (Join-Path $PSScriptRoot "Send-Heartbeat.ps1")

if (-not (docker compose ps --status running --services 2>$null | Select-String -Pattern "^backend$" -Quiet)) {
    Write-Host "[JobPilot stale check] Backend container isn't running - skipping."
    exit 0
}

Write-Host "[JobPilot stale check] Checking for stale applications..."
docker compose exec -T backend python -m app.scripts.check_stale_applications

if ($LASTEXITCODE -ne 0) {
    Send-Heartbeat -JobName "stale_check" -Status "error" -Detail "check_stale_applications exited non-zero"
    Write-Error "[JobPilot stale check] Script exited with an error - see output above."
    exit 1
}

Send-Heartbeat -JobName "stale_check" -Status "ok"
Write-Host "[JobPilot stale check] Done."
