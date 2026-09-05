# Runs the same job-matching sweep the app runs on demand
# (GET /jobs/search/auto-import), for every user, straight inside the
# backend container - so new matches (and their push notification) show
# up on their own, without you having to open JobPilot and ask for them.
# Safe to double-click/run any time; it only imports genuinely new
# postings. Scheduled every 2 hours while the app is on
# (install-job-sweep-schedule.ps1), and also run once immediately
# whenever the app is turned on (jobpilot-control.ps1 / start-jobpilot.bat)
# so a stretch of being off doesn't mean missing a sweep - it just runs
# late, right when you next power on.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
Set-Location $repoDir
. (Join-Path $PSScriptRoot "Send-Heartbeat.ps1")

if (-not (docker compose ps --status running --services 2>$null | Select-String -Pattern "^backend$" -Quiet)) {
    Write-Host "[JobPilot sweep] Backend container isn't running - skipping."
    exit 0
}

Write-Host "[JobPilot sweep] Running daily job-search sweep..."
docker compose exec -T backend python -m app.scripts.run_daily_sweep

if ($LASTEXITCODE -ne 0) {
    Send-Heartbeat -JobName "job_sweep" -Status "error" -Detail "run_daily_sweep exited non-zero"
    Write-Error "[JobPilot sweep] Sweep script exited with an error - see output above."
    exit 1
}

Send-Heartbeat -JobName "job_sweep" -Status "ok"
Write-Host "[JobPilot sweep] Done."
