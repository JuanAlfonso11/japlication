# Schedules watchdog.ps1 to run every 15 minutes via Task Scheduler, so a
# crashed container or a Docker Desktop that didn't restart after a reboot
# gets noticed and retried on its own, without you having to check.
# -MultipleInstances IgnoreNew skips a run if the previous one is somehow
# still going (e.g. waiting on a slow Docker Desktop startup), instead of
# piling up overlapping checks.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
$watchdogScript = Join-Path $repoDir "scripts\watchdog.ps1"
$taskName = "JobPilot Watchdog"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$watchdogScript`""

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Checks JobPilot is up every 15 min and self-heals if not (scripts\watchdog.ps1)." | Out-Null

Write-Host "Installed: '$taskName' scheduled task, runs every 15 minutes."
Write-Host "Activity log (only written when something needed fixing): logs\watchdog.log"
Write-Host "To undo, run: Unregister-ScheduledTask -TaskName '$taskName'"
