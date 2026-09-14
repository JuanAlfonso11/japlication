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

# Regenerate whenever the source PNG is newer than the .ico. The old
# condition was "only if the .ico does not exist yet", so a rebrand kept
# the previous icon on the Desktop forever: the shortcut still showed the
# violet mark long after the app itself had gone graphite, and re-running
# this script did nothing to fix it.
#
# This is only a fallback. `frontend/scripts/generate-icons.mjs`
# (npm run icons) writes a crisp multi-resolution .ico straight to
# $icoPath, which is why the timestamp check leaves a newer file alone —
# System.Drawing's GetHicon always yields a single 32x32 frame, so what
# it produces looks upscaled and soft in every large Desktop view.
Add-Type -AssemblyName System.Drawing
$icoIsStale = (Test-Path $iconSource) -and (
    (-not (Test-Path $icoPath)) -or
    ((Get-Item $iconSource).LastWriteTime -gt (Get-Item $icoPath).LastWriteTime)
)
if ($icoIsStale) {
    $bmp = [System.Drawing.Bitmap]::FromFile($iconSource)
    $icon = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
    $fileStream = [System.IO.File]::Create($icoPath)
    $icon.Save($fileStream)
    $fileStream.Close()
    $icon.Dispose()
    $bmp.Dispose()
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
