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
| `daily-job-sweep.ps1` | Runs the same job-matching sweep as the app's "search for matches" (`GET /jobs/search/auto-import`), for every user, straight inside the backend container — so new matches (and their push notification) show up even on a day JobPilot never gets opened. |
| `install-job-sweep-schedule.ps1` | Run once: schedules `daily-job-sweep.ps1` to run daily at 8 AM via Task Scheduler (task name "JobPilot Daily Job Sweep"). Already installed. |
| `watchdog.ps1` | Checks all 3 containers (db, backend, frontend) are actually running; if not, retries the same recovery steps as Encender (start Docker Desktop if needed, `docker compose up -d`). Logs every recovery attempt to `logs\watchdog.log` (silent when everything's already healthy). If recovery still fails, shows a Windows notification — it can't push to your phone for this one case, since the backend (what would send that push) is the thing that's down. |
| `install-watchdog-schedule.ps1` | Run once: schedules `watchdog.ps1` to run every 15 minutes via Task Scheduler (task name "JobPilot Watchdog"). Already installed. |
| `offline-page/serve-offline.ps1` | A tiny always-on static server (`http://localhost:3001`) for `offline-page/offline.html` — the "JobPilot está descansando" page with the sleepy card-mascot animation. Runs independently of Docker/JobPilot itself, so it can answer even while the real app is off. Auto-reloads itself every 5s, so once JobPilot comes back up the tab picks up the real app with no manual refresh. |
| `install-offline-page-autostart.ps1` | Run once: reserves `http://+:3001/` (one-time admin approval via UAC — needed so the server can accept any Host header, since `tailscale serve` forwards the real one) and registers the server to start at login. Already installed. |

**Encender/Apagar now also flip where `tailscale serve` points** `https://jobpilot.tailb3d4c1.ts.net` (port 443): at `localhost:3000` (the real frontend) when on, at `localhost:3001` (the offline page above) when off — both `jobpilot-control.ps1`'s buttons and `start-jobpilot.bat` do this. So opening the app while it's off shows the mascot page instead of a bare connection error, and it self-corrects to the real app once you hit Encender.

Note the two "start" paths overlap on purpose: **autostart** brings the app up silently at login with no window; the **desktop shortcut** is for manually turning it on/off afterward (e.g. after using Apagar, or on a PC that doesn't have autostart installed).

`backups/` is gitignored — it holds real user data (career profile, applications) and is never committed.

To restore a backup: `Get-Content backups\jobflow_<timestamp>.sql | docker compose exec -T db psql -U jobflow -d jobflow`
(stop the backend first so it isn't writing mid-restore).

**Drill-tested (2026-09-03)**: took a real `pg_dump`, restored it into a throwaway
`jobflow_restore_test` database on the same running container (never touched the live `jobflow`
database), and confirmed every table's row count matched exactly with no errors, before dropping
the scratch database. To repeat that drill instead of restoring straight into the live database:
```powershell
docker compose exec -T db psql -U jobflow -d jobflow -c "CREATE DATABASE jobflow_restore_test;"
Get-Content backups\jobflow_<timestamp>.sql | docker compose exec -T db psql -U jobflow -d jobflow_restore_test
docker compose exec -T db psql -U jobflow -d jobflow_restore_test -c "SELECT count(*) FROM users;"  # spot-check
docker compose exec -T db psql -U jobflow -d jobflow -c "DROP DATABASE jobflow_restore_test;"
```

## Pre-commit hook

`.githooks/pre-commit` runs the backend test suite before every commit
(skips gracefully if the backend container isn't running — never blocks a
commit over Docker being off). `core.hooksPath` is a local git config, not
versioned, so **after a fresh clone run once**: `git config core.hooksPath .githooks`
(already configured on this machine). Bypass a single commit with `git commit --no-verify`.

