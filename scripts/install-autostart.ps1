# Registers start-jobpilot.bat to run automatically every time you log into
# Windows, by placing a shortcut in your Startup folder. Run this once
# (right-click > Run with PowerShell, or from a terminal). To undo, delete
# the shortcut it creates, or run uninstall-autostart.ps1.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
$targetScript = Join-Path $repoDir "scripts\start-jobpilot.bat"
$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "JobPilot.lnk"

if (-not (Test-Path $targetScript)) {
    Write-Error "Could not find $targetScript"
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetScript
$shortcut.WorkingDirectory = $repoDir
$shortcut.WindowStyle = 7  # minimized
$shortcut.Description = "Starts the JobPilot app (Docker Desktop + docker compose)"
$shortcut.Save()

Write-Host "Installed: JobPilot will now start automatically when you log in."
Write-Host "Shortcut: $shortcutPath"
Write-Host "To undo, run scripts\uninstall-autostart.ps1 or delete that shortcut."
