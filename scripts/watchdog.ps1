# Checks every service (db, backend, frontend) is actually running, and if
# not, tries to bring the stack back up itself - same recovery steps as the
# Encender button (start Docker Desktop if needed, `docker compose up -d`).
# Meant to run unattended on a short interval (see
# install-watchdog-schedule.ps1), so a crashed container or a PC that
# rebooted without you around gets fixed on its own within minutes instead
# of silently staying down.
#
# If the stack is STILL not fully up after that recovery attempt, shows a
# Windows notification (Docker Desktop being broken, out of disk, etc. isn't
# something this script can fix by itself - only alerts, doesn't push to
# your phone, since the very thing that would send that push is what's
# down). Logs every recovery attempt (success or failure) to logs\watchdog.log
# - a healthy check writes nothing, so the log only grows when something
# actually happened.

$ErrorActionPreference = "Stop"

$RepoDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "Send-Heartbeat.ps1")
$DockerDesktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
$LogDir = Join-Path $RepoDir "logs"
$LogFile = Join-Path $LogDir "watchdog.log"
$ExpectedServices = @("db", "backend", "frontend")

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

function Write-Log([string]$Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -Path $LogFile -Value $line
}

function Test-AllServicesRunning {
    # Do NOT redirect stderr on a native command here (2>, *>) - PowerShell
    # 5.1 wraps any stderr line into a terminating ErrorRecord even on a
    # successful exit code, which would abort this script under
    # $ErrorActionPreference = "Stop".
    $running = @(docker compose ps --status running --services)
    foreach ($svc in $ExpectedServices) {
        if ($running -notcontains $svc) { return $false }
    }
    return $true
}

function Show-Notification([string]$Text) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $icon = New-Object System.Windows.Forms.NotifyIcon
    try {
        $icon.Icon = [System.Drawing.SystemIcons]::Warning
        $icon.Visible = $true
        $icon.BalloonTipTitle = "JobPilot"
        $icon.BalloonTipText = $Text
        $icon.ShowBalloonTip(15000)
        Start-Sleep -Seconds 16
    } finally {
        $icon.Dispose()
    }
}

Set-Location $RepoDir

if (Test-AllServicesRunning) {
    Send-Heartbeat -JobName "watchdog" -Status "ok"
    exit 0
}

Write-Log "Stack not fully up - attempting recovery."

docker info | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log "Docker Desktop isn't running - starting it."
    Start-Process $DockerDesktop
    $attempts = 0
    while ($attempts -lt 40) {
        Start-Sleep -Seconds 3
        docker info | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        $attempts++
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Recovery FAILED - Docker Desktop did not come up after 2 minutes."
        Show-Notification "Docker Desktop no arranco. Abrelo manualmente para levantar JobPilot."
        exit 1
    }
}

docker compose up -d | Out-Null
Start-Sleep -Seconds 10

if (Test-AllServicesRunning) {
    Write-Log "Recovery succeeded - all services back up."
    Send-Heartbeat -JobName "watchdog" -Status "ok" -Detail "recovered automatically"
    exit 0
}

Write-Log "Recovery FAILED - services still not all running after 'docker compose up -d'."
Show-Notification "JobPilot no pudo recuperarse solo. Abre el panel de control o revisa Docker Desktop."
exit 1
