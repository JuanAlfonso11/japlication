# Runs the same job-matching sweep the app runs on demand
# (GET /jobs/search/auto-import), for every user, straight inside the
# backend container - so new matches (and their push notification) show
# up even on a day you never open JobPilot. Safe to double-click/run any
# time; it only imports genuinely new postings.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
Set-Location $repoDir

if (-not (docker compose ps --status running --services 2>$null | Select-String -Pattern "^backend$" -Quiet)) {
    Write-Host "[JobPilot sweep] Backend container isn't running - skipping."
    exit 0
}

Write-Host "[JobPilot sweep] Running daily job-search sweep..."
docker compose exec -T backend python -m app.scripts.run_daily_sweep

if ($LASTEXITCODE -ne 0) {
    Write-Error "[JobPilot sweep] Sweep script exited with an error - see output above."
    exit 1
}

Write-Host "[JobPilot sweep] Done."
