# Schedules daily-job-sweep.ps1 to run automatically every day at 8 AM via
# Windows Task Scheduler - so new matching jobs (and the push notification
# about them) show up even on a day JobPilot never gets opened. Runs only
# while you're logged in (Docker Desktop needs your user session) - if the
# PC is off or asleep at 8 AM, it catches up the next time you log in
# instead of silently skipping the day. Picked 8 AM (5 hours after the 3
# AM DB backup) so it doesn't compete with it for Docker/DB load.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
$sweepScript = Join-Path $repoDir "scripts\daily-job-sweep.ps1"
$taskName = "JobPilot Daily Job Sweep"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$sweepScript`""

$trigger = New-ScheduledTaskTrigger -Daily -At 8am
$trigger.StartBoundary = [DateTime]::Today.AddHours(8).ToString("yyyy-MM-ddTHH:mm:ss")

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Daily job-matching sweep for every JobPilot user (scripts\daily-job-sweep.ps1)." | Out-Null

Write-Host "Installed: '$taskName' scheduled task, runs daily at 8 AM."
Write-Host "To undo, run: Unregister-ScheduledTask -TaskName '$taskName'"
