# Backs up the JobPilot Postgres database to scripts\..\backups\ as a
# timestamped .sql file, then deletes backups older than $RetentionDays.
# Run manually any time, or scheduled automatically (see
# install-backup-schedule.ps1, which runs this daily at 3 AM).

$ErrorActionPreference = "Stop"

$RetentionDays = 30

$repoDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "Send-Heartbeat.ps1")
$backupDir = Join-Path $repoDir "backups"
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backupFile = Join-Path $backupDir "jobflow_$timestamp.sql"

Set-Location $repoDir

Write-Host "[JobPilot backup] Dumping database..."
docker compose exec -T db pg_dump -U jobflow -d jobflow --no-owner --no-privileges > $backupFile

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $backupFile) -or (Get-Item $backupFile).Length -eq 0) {
    Send-Heartbeat -JobName "backup" -Status "error" -Detail "pg_dump failed or produced an empty file"
    Write-Error "[JobPilot backup] pg_dump failed or produced an empty file."
    if (Test-Path $backupFile) { Remove-Item $backupFile -Force }
    exit 1
}

$sizeKB = [math]::Round((Get-Item $backupFile).Length / 1KB, 1)
Send-Heartbeat -JobName "backup" -Status "ok" -Detail "$sizeKB KB"
Write-Host "[JobPilot backup] Saved $backupFile ($sizeKB KB)"

$cutoff = (Get-Date).AddDays(-$RetentionDays)
$old = Get-ChildItem $backupDir -Filter "jobflow_*.sql" | Where-Object { $_.LastWriteTime -lt $cutoff }
if ($old) {
    $old | Remove-Item -Force
    Write-Host "[JobPilot backup] Removed $($old.Count) backup(s) older than $RetentionDays days."
}

# Same retention window applied to error_logs. That table only ever grows,
# and while a handful of rows a week is nothing, one component crashing in a
# render loop can write a burst of them. Pruning here rather than in the API
# keeps the write path fast and puts all the housekeeping in the one job
# that already runs daily and already talks to the database.
#
# Deliberately after the dump above: a row is preserved in that night's
# backup before it's deleted here, so nothing is lost outright.
Write-Host "[JobPilot backup] Pruning error_logs older than $RetentionDays days..."
$ErrorActionPreference = "Continue"
docker compose exec -T db psql -U jobflow -d jobflow -c "DELETE FROM error_logs WHERE created_at < now() - interval '$RetentionDays days';" 2>&1 | ForEach-Object { Write-Host $_ }
$ErrorActionPreference = "Stop"
