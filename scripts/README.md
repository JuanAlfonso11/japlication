# JobPilot ops scripts

| Script | What it does |
|---|---|
| `start-jobpilot.bat` | Double-click to start everything (launches Docker Desktop if needed, then `docker compose up -d`). Also what autostart runs. |
| `install-autostart.ps1` | Run once: registers `start-jobpilot.bat` to run automatically at every Windows login (Startup folder shortcut). Already installed. |
| `uninstall-autostart.ps1` | Removes that autostart shortcut. |
| `backup-db.ps1` | Dumps the Postgres database to `backups/jobflow_<timestamp>.sql`, deletes backups older than 30 days. |
| `install-backup-schedule.ps1` | Run once: schedules `backup-db.ps1` to run daily at 3 AM via Task Scheduler (task name "JobPilot DB Backup"). Already installed. |

`backups/` is gitignored — it holds real user data (career profile, applications) and is never committed.

To restore a backup: `Get-Content backups\jobflow_<timestamp>.sql | docker compose exec -T db psql -U jobflow -d jobflow`
(stop the backend first so it isn't writing mid-restore).
