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
    [string]$VersionName,
    # Builds a release-signed APK instead of a debug-signed one.
    #
    # NOT the default, and it must stay that way until you decide to switch:
    # Android refuses to install an APK whose signing certificate differs
    # from the installed one, so the FIRST release-signed build cannot
    # update anybody. Every device (yours and every tester's) has to
    # uninstall JobPilot and install fresh, once. Nothing is lost when they
    # do - all state lives on the server - but it is a coordinated step, not
    # something to trip over by accident.
    #
    # After that first switch, keep using -Release forever: going back to
    # debug signing would have the same problem in reverse.
    [switch]$Release
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

$gradleTask = if ($Release) { "assembleRelease" } else { "assembleDebug" }
Write-Host "[ship] Building APK (gradlew $gradleTask)..."

if ($Release) {
    $keystoreProps = Join-Path $repoDir "frontend\android\keystore.properties"
    if (-not (Test-Path $keystoreProps)) {
        throw "Falta frontend\android\keystore.properties. Corre .\scripts\create-release-keystore.ps1 primero."
    }
}

Push-Location (Join-Path $repoDir "frontend\android")
try {
    .\gradlew.bat $gradleTask
    if ($LASTEXITCODE -ne 0) { throw "gradlew $gradleTask failed" }
} finally {
    Pop-Location
}

$apkSource = if ($Release) {
    Join-Path $repoDir "frontend\android\app\build\outputs\apk\release\app-release.apk"
} else {
    Join-Path $repoDir "frontend\android\app\build\outputs\apk\debug\app-debug.apk"
}
$apkDest = Join-Path $repoDir "scripts\apk-server\jobpilot.apk"
Copy-Item -Path $apkSource -Destination $apkDest -Force
Write-Host "[ship] Copied APK to $apkDest"

Write-Host "[ship] Updating .env..."
$envPath = Join-Path $repoDir ".env"
# UTF-8 both ways: Windows PowerShell 5.1 defaults to ANSI and mangled
# accented letters in the update notes. WriteAllText writes UTF-8 without a BOM.
$envContent = Get-Content $envPath -Raw -Encoding UTF8
$envContent = $envContent -replace 'ANDROID_LATEST_VERSION_CODE=.*', "ANDROID_LATEST_VERSION_CODE=$newCode"
$envContent = $envContent -replace 'ANDROID_LATEST_VERSION_NAME=.*', "ANDROID_LATEST_VERSION_NAME=$VersionName"
$envContent = $envContent -replace 'ANDROID_UPDATE_NOTES=.*', "ANDROID_UPDATE_NOTES=$Notes"
[IO.File]::WriteAllText($envPath, $envContent)

Write-Host "[ship] Restarting backend so it picks up the new .env values..."
# `docker compose` writes its progress lines ("Container cld-db-1 Running")
# to stderr even on success. Under $ErrorActionPreference = "Stop" that
# turns into a terminating NativeCommandError, so this script reported
# failure — exit code 1, red text — every single time, *after* having
# already done all its work. Drop to "Continue" for the native call and
# judge success the only way that's meaningful here: $LASTEXITCODE.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    docker compose up -d backend 2>&1 | ForEach-Object { Write-Host $_ }
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($LASTEXITCODE -ne 0) { throw "docker compose up -d backend failed" }

Write-Host ""
Write-Host "[ship] Done. version_code=$newCode version_name=$VersionName now live at GET /app/android-update."
Write-Host "[ship] The phone (Tailscale connected, Wi-Fi or mobile data) will see the update prompt within 30 min, or immediately on next app open."
