# Creates a "JobPilot" shortcut on the Desktop, pointing at JobPilot.vbs
# (the silent launcher for jobpilot-control.ps1), using the app's own icon.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $PSScriptRoot
$vbsPath = Join-Path $repoDir "scripts\JobPilot.vbs"
$iconSource = Join-Path $repoDir "frontend\public\icons\icon-192.png"
$iconDir = Join-Path $repoDir "scripts\.icon"
$icoPath = Join-Path $iconDir "jobpilot.ico"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "JobPilot.lnk"

if (-not (Test-Path $iconDir)) { New-Item -ItemType Directory -Path $iconDir | Out-Null }

Add-Type -AssemblyName System.Drawing
if ((Test-Path $iconSource) -and -not (Test-Path $icoPath)) {
    $bmp = [System.Drawing.Bitmap]::FromFile($iconSource)
    $icon = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
    $fileStream = [System.IO.File]::Create($icoPath)
    $icon.Save($fileStream)
    $fileStream.Close()
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $vbsPath
$shortcut.WorkingDirectory = $repoDir
$shortcut.WindowStyle = 1
$shortcut.Description = "Encender o apagar JobPilot"
if (Test-Path $icoPath) { $shortcut.IconLocation = $icoPath }
$shortcut.Save()

Write-Host "Installed: $shortcutPath"
