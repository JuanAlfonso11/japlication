# Registers the APK update server (scripts\apk-server\serve-apk.ps1) to
# start automatically at Windows login, same pattern as the offline
# placeholder page's own autostart (install-offline-page-autostart.ps1).
# This is what makes the in-app "there's an update" banner's download
# link (https://jobpilot.tailb3d4c1.ts.net:10000) work without needing the
# phone plugged in by cable. Run once.

$ErrorActionPreference = "Stop"

$repoDir = $PSScriptRoot
$targetScript = Join-Path $repoDir "apk-server\serve-apk.vbs"

# serve-apk.ps1 binds to http://+:8446/ (any Host header) rather than
# http://localhost:8446/ -- that "+" wildcard needs a one-time URL ACL
# reservation to be usable without running the server elevated. This
# triggers a UAC prompt (one admin approval, once); the server itself
# keeps running as your normal user afterward.
$existing = netsh http show urlacl url=http://+:8446/ 2>&1
if ($existing -notmatch "Reserved URL") {
    Write-Host "Requesting one-time admin approval to reserve http://+:8446/ ..."
    $cmd = "netsh http add urlacl url=http://+:8446/ user=$env:USERDOMAIN\$env:USERNAME"
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile", "-Command", $cmd -Wait
}

$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "JobPilot APK Server.lnk"

if (-not (Test-Path $targetScript)) {
    Write-Error "Could not find $targetScript"
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetScript
$shortcut.WorkingDirectory = Join-Path $repoDir "apk-server"
$shortcut.WindowStyle = 7  # minimized
$shortcut.Description = "Serves JobPilot's latest Android APK on localhost:8446 for the in-app update banner"
$shortcut.Save()

# tailscale funnel's mapping persists in tailscaled's own config across
# reboots (unlike the HttpListener above, which is just a normal process)
# -- set once here, never needs to run again after this.
$Tailscale = "C:\Program Files\Tailscale\tailscale.exe"
& $Tailscale funnel --bg --https=10000 http://localhost:8446 *> $null

Write-Host "Installed: the APK update server will now start automatically when you log in."
Write-Host "Shortcut: $shortcutPath"
Write-Host "Serving at: https://jobpilot.tailb3d4c1.ts.net:10000/"
Write-Host "To undo: delete that shortcut, and run 'tailscale funnel --https=10000 off'."
