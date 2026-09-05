# One-command "ship a new APK" pipeline — run this after any change that
# actually needs a new native build (capacitor.config.ts, AndroidManifest,
# a native plugin, the app icon, ...). Most changes DON'T need this: the
# app is a thin native shell that loads the live frontend/backend over
# Tailscale (see frontend/capacitor.config.ts), so a plain
# `docker compose up -d --build backend frontend` already reaches the
# phone on its next reload/poll with zero APK involved.
#
# What this does, in order:
#   1. Bumps android/app/build.gradle's versionCode (+1) and versionName.
#   2. npx cap sync android (copies webDir assets + plugin config).
#   3. gradlew assembleDebug (the actual APK build).
#   4. Copies the built APK to scripts/apk-server/jobpilot.apk (the file
#      serve-apk.ps1 always serves — no restart needed for that server).
#   5. Updates .env's ANDROID_LATEST_VERSION_CODE/NAME/NOTES to match.
#   6. Restarts the backend container so GET /app/android-update reflects
#      the new version immediately.
#
# From there, UpdateChecker.tsx (polls every 30 min, and on app open)
# notices the new version_code on its own and prompts the user in-app —
# nothing else to do. The phone just needs Tailscale connected (Wi-Fi or
# mobile data, doesn't matter which) to download it.
#
# Usage:
#   .\scripts\ship-android-update.ps1 -Notes "Lo que cambio, en una frase para el usuario"
#   .\scripts\ship-android-update.ps1 -Notes "..." -VersionName "1.4"   # override the auto-bump

param(
    [Parameter(Mandatory)] [string]$Notes,
    [string]$VersionName
)

$ErrorActionPreference = "Stop"
$repoDir = Split-Path -Parent $PSScriptRoot
Set-Location $repoDir

# Fresh PowerShell processes on this machine don't reliably inherit
# JAVA_HOME/ANDROID_HOME/node's PATH entry from setx'd user env vars (seen
# repeatedly this project) — set them explicitly here rather than assume.
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot"
$env:ANDROID_HOME = "C:\Users\Juana\AppData\Local\Android\Sdk"
$env:Path += ";C:\Program Files\nodejs"

$buildGradlePath = Join-Path $repoDir "frontend\android\app\build.gradle"
$buildGradle = Get-Content $buildGradlePath -Raw

$currentCodeMatch = [regex]::Match($buildGradle, 'versionCode\s+(\d+)')
$currentNameMatch = [regex]::Match($buildGradle, 'versionName\s+"([^"]+)"')
if (-not $currentCodeMatch.Success -or -not $currentNameMatch.Success) {
    throw "Could not find versionCode/versionName in $buildGradlePath"
}
$newCode = [int]$currentCodeMatch.Groups[1].Value + 1
$oldName = $currentNameMatch.Groups[1].Value

if (-not $VersionName) {
    # Auto-bump the minor number: "1.3" -> "1.4". Falls back to appending
    # ".1" if the current name isn't in that exact "major.minor" shape.
    if ($oldName -match '^(\d+)\.(\d+)$') {
        $VersionName = "$($Matches[1]).$([int]$Matches[2] + 1)"
    } else {
        $VersionName = "$oldName.1"
    }
}

Write-Host "[ship] versionCode $($currentCodeMatch.Groups[1].Value) -> $newCode, versionName $oldName -> $VersionName"

$buildGradle = $buildGradle -replace 'versionCode\s+\d+', "versionCode $newCode"
$buildGradle = $buildGradle -replace 'versionName\s+"[^"]+"', "versionName `"$VersionName`""
Set-Content -Path $buildGradlePath -Value $buildGradle -NoNewline

Write-Host "[ship] Syncing Capacitor..."
Push-Location (Join-Path $repoDir "frontend")
try {
    npx cap sync android
    if ($LASTEXITCODE -ne 0) { throw "cap sync failed" }
} finally {
    Pop-Location
}

Write-Host "[ship] Building APK (gradlew assembleDebug)..."
Push-Location (Join-Path $repoDir "frontend\android")
try {
    .\gradlew.bat assembleDebug
    if ($LASTEXITCODE -ne 0) { throw "gradlew assembleDebug failed" }
} finally {
    Pop-Location
}

$apkSource = Join-Path $repoDir "frontend\android\app\build\outputs\apk\debug\app-debug.apk"
$apkDest = Join-Path $repoDir "scripts\apk-server\jobpilot.apk"
Copy-Item -Path $apkSource -Destination $apkDest -Force
Write-Host "[ship] Copied APK to $apkDest"

Write-Host "[ship] Updating .env..."
$envPath = Join-Path $repoDir ".env"
$envContent = Get-Content $envPath -Raw
$envContent = $envContent -replace 'ANDROID_LATEST_VERSION_CODE=.*', "ANDROID_LATEST_VERSION_CODE=$newCode"
$envContent = $envContent -replace 'ANDROID_LATEST_VERSION_NAME=.*', "ANDROID_LATEST_VERSION_NAME=$VersionName"
$envContent = $envContent -replace 'ANDROID_UPDATE_NOTES=.*', "ANDROID_UPDATE_NOTES=$Notes"
Set-Content -Path $envPath -Value $envContent -NoNewline

Write-Host "[ship] Restarting backend so it picks up the new .env values..."
docker compose up -d backend
if ($LASTEXITCODE -ne 0) { throw "docker compose up -d backend failed" }

Write-Host ""
Write-Host "[ship] Done. version_code=$newCode version_name=$VersionName now live at GET /app/android-update."
Write-Host "[ship] The phone (Tailscale connected, Wi-Fi or mobile data) will see the update prompt within 30 min, or immediately on next app open."
