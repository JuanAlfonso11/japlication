# JobPilot ops scripts

| Script | What it does |
|---|---|
| **`JobPilot.vbs`** | The desktop shortcut's target — silently opens the 2-button control panel (`jobpilot-control.ps1`), no console window. |
| **`jobpilot-control.ps1`** | The control panel itself: a small window with **Encender** (connects Tailscale, starts Docker Desktop if needed, `docker compose up -d`) and **Apagar** (`docker compose stop`), with a live status dot. |
| `install-desktop-shortcut.ps1` | Run once: creates the `JobPilot` shortcut on the Desktop, using the app's icon. Already installed. |
| `start-jobpilot.bat` | Headless equivalent of the Encender button (no window) — used by autostart so login doesn't pop up a GUI. Also fine to run directly from a terminal. |
| `install-autostart.ps1` | Run once: registers `start-jobpilot.bat` to run automatically at every Windows login (Startup folder shortcut). Already installed. |
| `uninstall-autostart.ps1` | Removes that autostart entry. |
| `backup-db.ps1` | Dumps the Postgres database to `backups/jobflow_<timestamp>.sql`, deletes backups older than 30 days. |
| `install-backup-schedule.ps1` | Run once: schedules `backup-db.ps1` to run daily at 3 AM via Task Scheduler (task name "JobPilot DB Backup"). Already installed. |

Note the two "start" paths overlap on purpose: **autostart** brings the app up silently at login with no window; the **desktop shortcut** is for manually turning it on/off afterward (e.g. after using Apagar, or on a PC that doesn't have autostart installed).

`backups/` is gitignored — it holds real user data (career profile, applications) and is never committed.

To restore a backup: `Get-Content backups\jobflow_<timestamp>.sql | docker compose exec -T db psql -U jobflow -d jobflow`
(stop the backend first so it isn't writing mid-restore).
