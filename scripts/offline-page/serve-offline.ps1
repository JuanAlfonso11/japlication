# Tiny always-on static server for offline.html ("JobPilot esta
# descansando" + mascota) on http://localhost:3001. Runs independently of
# Docker/JobPilot itself (started at Windows login, like the app's own
# autostart) so it's always available to answer, even while the real
# containers are stopped.
#
# jobpilot-control.ps1's Encender/Apagar buttons point `tailscale serve`'s
# https:443 target at this port (offline) or at localhost:3000 (the real
# frontend) depending on state - this script never needs to know which;
# it just always serves the same page.

$ErrorActionPreference = "Stop"

# "+" (not "localhost") so it answers regardless of the incoming Host
# header -- tailscale serve forwards the original Host
# (jobpilot.tailb3d4c1.ts.net), which an HttpListener bound to literally
# "localhost:3001" rejects with 400 Bad Request. Needs a one-time URL ACL
# reservation to bind without running elevated -- see
# install-offline-page-autostart.ps1.
$htmlPath = Join-Path $PSScriptRoot "offline.html"
$prefix = "http://+:3001/"

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add($prefix)
$listener.Start()

Write-Host "[JobPilot offline page] Listening on $prefix"

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        try {
            $html = Get-Content -Raw -Encoding UTF8 -Path $htmlPath
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($html)
            $context.Response.StatusCode = 200
            $context.Response.ContentType = "text/html; charset=utf-8"
            $context.Response.ContentLength64 = $bytes.Length
            $context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
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
