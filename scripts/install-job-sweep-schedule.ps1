# Schedules daily-job-sweep.ps1 to run automatically every 2 hours via
# Windows Task Scheduler - so new matching jobs (and the push notification
# about them) keep showing up on their own, without you having to open
# JobPilot and ask for them. Runs only while you're logged in (Docker
# Desktop needs your user session) - if the PC/app is off, it simply
# doesn't fire; jobpilot-control.ps1 / start-jobpilot.bat run one sweep
# immediately every time the app is turned back on, so a stretch of being
# off just means that sweep runs late instead of being lost.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
$sweepScript = Join-Path $repoDir "scripts\daily-job-sweep.ps1"
$taskName = "JobPilot Job Sweep"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$sweepScript`""

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 2) -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
# Old name from when this ran once a day - remove it too, if present, so
# there's never a stale duplicate task left behind.
Unregister-ScheduledTask -TaskName "JobPilot Daily Job Sweep" -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Job-matching sweep for every JobPilot user, every 2 hours (scripts\daily-job-sweep.ps1)." | Out-Null

Write-Host "Installed: '$taskName' scheduled task, runs every 2 hours."
Write-Host "To undo, run: Unregister-ScheduledTask -TaskName '$taskName'"
