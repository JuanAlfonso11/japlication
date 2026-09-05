# Shared helper, dot-sourced by the scheduled scripts (daily-job-sweep.ps1,
# check-stale-applications.ps1, backup-db.ps1, watchdog.ps1) to report
# "I ran, here's how it went" to the backend's POST /system/heartbeat —
# powers Profile's "Estado del sistema" panel. Always wrapped in try/catch
# by design: a heartbeat POST failing (e.g. backend briefly down) must
# never turn into a failure of the actual scheduled job that called it.
#
# The backend auto-generates SYSTEM_HEARTBEAT_SECRET on first startup and
# persists it to backend/runtime/heartbeat_secret (bind-mounted into the
# container at /app/runtime) — read that same file here so every scheduled
# script agrees with the backend without any manual secret setup.
function Get-HeartbeatSecret {
    $repoDir = Split-Path -Parent $PSScriptRoot
    $secretFile = Join-Path $repoDir "backend\runtime\heartbeat_secret"
    if (Test-Path $secretFile) {
        return (Get-Content $secretFile -Raw).Trim()
    }
    return $null
}

function Send-Heartbeat {
    param(
        [Parameter(Mandatory)] [string]$JobName,
        [string]$Status = "ok",
        [string]$Detail = ""
    )
    try {
        $body = @{ job_name = $JobName; status = $Status; detail = $Detail } | ConvertTo-Json
        $headers = @{}
        $secret = Get-HeartbeatSecret
        if ($secret) { $headers["X-Heartbeat-Secret"] = $secret }
        Invoke-RestMethod -Uri "http://localhost:8000/api/v1/system/heartbeat" `
            -Method Post -Body $body -ContentType "application/json" -Headers $headers -TimeoutSec 5 | Out-Null
    } catch {
        # Non-fatal — see comment above.
    }
}
