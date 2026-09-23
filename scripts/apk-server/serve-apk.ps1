# Always-on static server for the latest built Android APK, on
# http://localhost:8446 -- `tailscale funnel` maps
# https://jobpilot.tailb3d4c1.ts.net:10000 to this port (public; set up once, see
# docs/ANDROID_APP.md), which is what the in-app update banner
# (GET /app/android-update -> ANDROID_UPDATE_APK_URL) links to. Runs
# independently of Docker/JobPilot itself, same as offline-page's server,
# so an update stays downloadable even while the containers are stopped.
#
# Whenever a new native build ships: bump android/app/build.gradle's
# versionCode, run gradlew assembleDebug, copy the resulting
# app-debug.apk over jobpilot.apk in this folder (this script always
# serves whatever file is here, no restart needed), and update
# ANDROID_LATEST_VERSION_CODE/ANDROID_UPDATE_APK_URL in .env to match.

$ErrorActionPreference = "Stop"

# "+" (not "localhost") for the same reason as serve-offline.ps1: tailscale
# serve forwards the real Host header, which a listener bound to literally
# "localhost:8446" would reject. Needs a one-time URL ACL reservation --
# see install-apk-server-autostart.ps1.
$apkPath = Join-Path $PSScriptRoot "jobpilot.apk"
$prefix = "http://+:8446/"

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add($prefix)
$listener.Start()

Write-Host "[JobPilot APK server] Listening on $prefix, serving $apkPath"

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        try {
            if (Test-Path $apkPath) {
                $bytes = [System.IO.File]::ReadAllBytes($apkPath)
                $context.Response.StatusCode = 200
                $context.Response.ContentType = "application/vnd.android.package-archive"
                $context.Response.AddHeader("Content-Disposition", 'attachment; filename="jobpilot.apk"')
                $context.Response.ContentLength64 = $bytes.Length
                $context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
            } else {
                $context.Response.StatusCode = 404
            }
        } catch {
            # Never let one bad request kill the listener loop.
        } finally {
            $context.Response.OutputStream.Close()
        }
    }
} finally {
    $listener.Stop()
    $listener.Close()
}
