# Shared helper, dot-sourced by the scheduled scripts (daily-job-sweep.ps1,
# check-stale-applications.ps1, backup-db.ps1, watchdog.ps1) to report
# "I ran, here's how it went" to the backend's POST /system/heartbeat —
# powers Profile's "Estado del sistema" panel. Always wrapped in try/catch
# by design: a heartbeat POST failing (e.g. backend briefly down) must
# never turn into a failure of the actual scheduled job that called it.
function Send-Heartbeat {
    param(
        [Parameter(Mandatory)] [string]$JobName,
        [string]$Status = "ok",
        [string]$Detail = ""
    )
    try {
        $body = @{ job_name = $JobName; status = $Status; detail = $Detail } | ConvertTo-Json
        Invoke-RestMethod -Uri "http://localhost:8000/api/v1/system/heartbeat" `
            -Method Post -Body $body -ContentType "application/json" -TimeoutSec 5 | Out-Null
    } catch {
        # Non-fatal — see comment above.
    }
}
