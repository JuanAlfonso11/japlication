# Schedules backup-db.ps1 to run automatically every day at 3 AM via
# Windows Task Scheduler. Runs only while you're logged in (Docker Desktop
# needs your user session to reach the Docker engine) - if the PC is off or
# asleep at 3 AM, it catches up the next time you log in instead of
# silently skipping the day.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
$backupScript = Join-Path $repoDir "scripts\backup-db.ps1"
$taskName = "JobPilot DB Backup"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`""

$trigger = New-ScheduledTaskTrigger -Daily -At 3am
$trigger.StartBoundary = [DateTime]::Today.AddHours(3).ToString("yyyy-MM-ddTHH:mm:ss")

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Daily backup of the JobPilot Postgres database (scripts\backup-db.ps1)." | Out-Null

Write-Host "Installed: '$taskName' scheduled task, runs daily at 3 AM."
Write-Host "Backups land in: $repoDir\backups\ (30-day retention)"
Write-Host "To undo, run: Unregister-ScheduledTask -TaskName '$taskName'"
