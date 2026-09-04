# Removes the JobPilot autostart shortcut installed by install-autostart.ps1.

$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "JobPilot.lnk"

if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force
    Write-Host "Removed: JobPilot will no longer start automatically at login."
} else {
    Write-Host "Nothing to remove - no autostart shortcut was found."
}
