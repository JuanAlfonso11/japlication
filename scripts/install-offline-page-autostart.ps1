# Registers the offline placeholder page (scripts\offline-page\serve-offline.ps1)
# to start automatically at Windows login, same pattern as JobPilot's own
# autostart. This one needs to be separate from - and always running
# ahead of - JobPilot itself: it's what answers https://jobpilot...
# with the "JobPilot esta descansando" mascot page whenever the real app
# is turned off. Run once.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
$targetScript = Join-Path $repoDir "scripts\offline-page\serve-offline.vbs"

# serve-offline.ps1 binds to http://+:3001/ (any Host header, since
# tailscale serve forwards the real one) rather than http://localhost:3001/
# -- that "+" wildcard needs a one-time URL ACL reservation to be usable
# without running the server elevated. This triggers a UAC prompt (one
# admin approval, once); the server itself keeps running as your normal
# user afterward.
$existing = netsh http show urlacl url=http://+:3001/ 2>&1
if ($existing -notmatch "Reserved URL") {
    Write-Host "Requesting one-time admin approval to reserve http://+:3001/ ..."
    $cmd = "netsh http add urlacl url=http://+:3001/ user=$env:USERDOMAIN\$env:USERNAME"
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile", "-Command", $cmd -Wait
}
$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "JobPilot Offline Page.lnk"

if (-not (Test-Path $targetScript)) {
    Write-Error "Could not find $targetScript"
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetScript
$shortcut.WorkingDirectory = Join-Path $repoDir "scripts\offline-page"
$shortcut.WindowStyle = 7  # minimized
$shortcut.Description = "Serves JobPilot's offline placeholder page on localhost:3001"
$shortcut.Save()

Write-Host "Installed: the offline-page server will now start automatically when you log in."
Write-Host "Shortcut: $shortcutPath"
Write-Host "To undo: delete that shortcut."
