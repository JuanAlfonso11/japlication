# Backs up the JobPilot Postgres database to scripts\..\backups\ as a
# timestamped .sql file, then deletes backups older than $RetentionDays.
# Run manually any time, or scheduled automatically (see
# install-backup-schedule.ps1, which runs this daily at 3 AM).

$ErrorActionPreference = "Stop"

$RetentionDays = 30

$repoDir = Split-Path -Parent $PSScriptRoot
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
    Write-Error "[JobPilot backup] pg_dump failed or produced an empty file."
    if (Test-Path $backupFile) { Remove-Item $backupFile -Force }
    exit 1
}

$sizeKB = [math]::Round((Get-Item $backupFile).Length / 1KB, 1)
Write-Host "[JobPilot backup] Saved $backupFile ($sizeKB KB)"

$cutoff = (Get-Date).AddDays(-$RetentionDays)
$old = Get-ChildItem $backupDir -Filter "jobflow_*.sql" | Where-Object { $_.LastWriteTime -lt $cutoff }
if ($old) {
    $old | Remove-Item -Force
    Write-Host "[JobPilot backup] Removed $($old.Count) backup(s) older than $RetentionDays days."
}
