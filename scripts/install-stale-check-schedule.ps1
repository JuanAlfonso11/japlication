# Schedules check-stale-applications.ps1 to run once a day via Windows
# Task Scheduler, so a "no movement in 2 weeks" reminder shows up on its
# own. Runs only while you're logged in (same constraint as the job
# sweep) - if the PC is off that day, it just runs late the next time
# Windows Task Scheduler gets a chance (StartWhenAvailable below).

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
$checkScript = Join-Path $repoDir "scripts\check-stale-applications.ps1"
$taskName = "JobPilot Stale Application Check"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$checkScript`""

$trigger = New-ScheduledTaskTrigger -Daily -At "9:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Once-a-day check for applications with no movement in a while (scripts\check-stale-applications.ps1)." | Out-Null

Write-Host "Installed: '$taskName' scheduled task, runs daily at 9:00 AM."
Write-Host "To undo, run: Unregister-ScheduledTask -TaskName '$taskName'"
