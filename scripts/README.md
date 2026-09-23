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
| `daily-job-sweep.ps1` | Runs the same job-matching sweep as the app's "search for matches" (`GET /jobs/search/auto-import`), for every user, straight inside the backend container — so new matches (and their push notification) keep showing up on their own, without opening JobPilot to ask for them. |
| `install-job-sweep-schedule.ps1` | Run once: schedules `daily-job-sweep.ps1` to run every 2 hours via Task Scheduler (task name "JobPilot Job Sweep"), for as long as the app is on. Already installed. |
| `watchdog.ps1` | Checks all 3 containers (db, backend, frontend) are actually running; if not, retries the same recovery steps as Encender (start Docker Desktop if needed, `docker compose up -d`). Logs every recovery attempt to `logs\watchdog.log` (silent when everything's already healthy). If recovery still fails, shows a Windows notification — it can't push to your phone for this one case, since the backend (what would send that push) is the thing that's down. |
| `install-watchdog-schedule.ps1` | Run once: schedules `watchdog.ps1` to run every 15 minutes via Task Scheduler (task name "JobPilot Watchdog"). Already installed. |
| `check-stale-applications.ps1` | Runs the "did you follow up?" check inside the backend container (`backend/app/scripts/check_stale_applications.py`): applications stuck in `applied` with no movement in a while get a reminder. Once a day is enough — running it more often would just re-send the same reminder inside its own re-notify window. |
| `install-stale-check-schedule.ps1` | Run once: schedules `check-stale-applications.ps1` daily at 9 AM (task name "JobPilot Stale Application Check"). Already installed. |
| `Send-Heartbeat.ps1` | Not a job — a helper the scheduled scripts dot-source to report "I ran, here's how it went" to `POST /system/heartbeat`, which is what fills **Perfil → Estado del sistema**. Every call is wrapped in try/catch on purpose: the heartbeat failing (backend briefly down) must never turn into a failure of the job that sent it. Reads the shared secret from `backend/runtime/heartbeat_secret`, which the backend generates on first start — nothing to configure. |
| `offline-page/serve-offline.ps1` | A tiny always-on static server (`http://localhost:3001`) for `offline-page/offline.html` — the "JobPilot está descansando" page with the sleepy card-mascot animation. Runs independently of Docker/JobPilot itself, so it can answer even while the real app is off. Auto-reloads itself every 5s, so once JobPilot comes back up the tab picks up the real app with no manual refresh. |
| `install-offline-page-autostart.ps1` | Run once: reserves `http://+:3001/` (one-time admin approval via UAC — needed so the server can accept any Host header, since `tailscale serve` forwards the real one) and registers the server to start at login. Already installed. |
| `ship-android-update.ps1` | One-command pipeline for the rare case a code change actually needs a new native APK (capacitor.config.ts, AndroidManifest, a native plugin, the icon — NOT a normal frontend/backend change, which already reaches the phone live the moment `docker compose up -d --build` runs, no APK involved). Bumps `build.gradle`'s versionCode/versionName, runs `cap sync` + `gradlew assembleDebug`, copies the APK to `apk-server/jobpilot.apk`, updates `.env`'s `ANDROID_LATEST_VERSION_*`/`ANDROID_UPDATE_NOTES`, and restarts the backend. From there `UpdateChecker.tsx` (in-app, polls every 30 min + on open) picks it up on its own — nothing to do on the phone side beyond having Tailscale connected. Usage: `.\scripts\ship-android-update.ps1 -Notes "lo que cambió, en una frase"` (add `-VersionName "1.5"` to override the auto minor-version bump). |
| `apk-server/serve-apk.ps1` | Always-on static server on `http://localhost:8446` that hands out `apk-server/jobpilot.apk` — what the in-app update banner downloads. `tailscale serve` maps `https://<host>.ts.net:8444` to it. Runs outside Docker (like the offline page), so an update stays downloadable even while the containers are stopped. No authentication: anything on the tailnet can fetch it, which is fine because the APK is a WebView shell with no secrets in it — but it must never be exposed with `tailscale funnel`. |
| `install-apk-server-autostart.ps1` | Run once: reserves `http://+:8446/` (one-time UAC prompt — needed so the listener accepts the real Host header `tailscale serve` forwards), registers the server to start at login, and adds the `--https=8444` serve route. Already installed. |
| `create-release-keystore.ps1` | Run once: creates a real release signing key for the Android app, instead of the SDK's debug key (which lives at a known path with the password `android`, and is silently regenerated if lost — at which point no existing install can ever be updated again). Back up what it produces. |
| `lock-secrets.ps1` | Tightens NTFS permissions on the files that hold credentials or personal data (`.env`, `backups/`, `backend/secrets/`): breaks inheritance and leaves access to the current user and SYSTEM only. Idempotent; `-Verify` just reports, and `icacls <path> /reset /T` undoes it. |
| `check-schema-drift.ps1` | Loads `db/schema.sql` and the Alembic migrations into two throwaway databases and diffs the result. This catches a failure that is otherwise silent and permanent: `migrate.py` stamps a schema-loaded database as "already up to date", so any column that lived only in a migration would never be applied to a fresh volume. It really happened — 0006/0007 were out of `schema.sql` for weeks. |
| `check-tls-cert.ps1` | Reads the TLS certificate Tailscale actually serves on 443 and 8443 and warns while there's still time. Tailscale renews the Let's Encrypt cert on its own and almost always succeeds; the point is the case where it doesn't, which today has no alarm at all — the cert would expire in silence and the phone app would just stop loading. Warns at 21 days left, critical at 7, reports through `Send-Heartbeat`. Add `-Ports 443,8443,8444` to include the APK route. |
| `install-tls-cert-schedule.ps1` | Run once: schedules `check-tls-cert.ps1` weekly, Sundays at 10 AM (task name "JobPilot TLS Cert Check"). Weekly because the cert lasts 90 days and the warning fires at 21 left — a missed week still leaves two. |
| `check-deps.ps1` | Looks for known vulnerabilities in the dependencies that actually run: `npm audit --omit=dev` (high/critical) for the frontend, `pip-audit` over the `cld-backend` image (pytest ignored, it never serves a request). Reports through `Send-Heartbeat` as `deps_audit`. Exists because advisories appear without the code changing — Next 14 carried a public unauthenticated RCE here for months unnoticed. The pre-commit hook runs the npm half whenever `frontend/package*.json` is staged. |
| `install-deps-audit-schedule.ps1` | Run once: schedules `check-deps.ps1` weekly, Sundays at 10:15 AM (task name "JobPilot Dependency Audit"). |
| `fix-task-windows.ps1` | Repoints the scheduled tasks at `run-hidden.vbs` so they stop flashing a PowerShell console (Task Scheduler creates the window first and hides it after, which steals focus — several times an hour with the 15-minute watchdog). Safe to re-run. |
| `run-hidden.vbs` | The silent launcher those tasks use: `wscript` has no console of its own, so PowerShell started from here never creates a window. |

**Encender/Apagar now also flip where `tailscale serve` points** `https://jobpilot.tailb3d4c1.ts.net` (port 443): at `localhost:3000` (the real frontend) when on, at `localhost:3001` (the offline page above) when off — both `jobpilot-control.ps1`'s buttons and `start-jobpilot.bat` do this. So opening the app while it's off shows the mascot page instead of a bare connection error, and it self-corrects to the real app once you hit Encender.

**Turning the app on also fires an immediate job-matching sweep** (in the background, not blocking Encender/login) — on top of the every-2-hours schedule above, so any stretch of being off doesn't mean missing matches; the moment the app comes back on, the queue catches up right away instead of waiting for the next scheduled slot.

Note the two "start" paths overlap on purpose: **autostart** brings the app up silently at login with no window; the **desktop shortcut** is for manually turning it on/off afterward (e.g. after using Apagar, or on a PC that doesn't have autostart installed).

`backups/` is gitignored — it holds real user data (career profile, applications) and is never committed.

To restore a backup:
```powershell
docker compose cp backups\jobflow_<timestamp>.sql db:/tmp/restore.sql
docker compose exec -T db psql -U jobflow -d jobflow -v ON_ERROR_STOP=1 -f /tmp/restore.sql
```
(stop the backend first so it isn't writing mid-restore).

This used to read `Get-Content backups\... | psql`, and that pipe was hiding a
real problem. `backup-db.ps1` wrote the dump with `>`, which in Windows
PowerShell 5.1 — what the scheduled task runs — is `Out-File`, and `Out-File`
writes **UTF-16LE**. Every backup on disk was UTF-16: `ff fe` BOM, twice the
size (4,517,336 bytes for a 2,420,790-character dump). `Get-Content` detects
the BOM and decodes it, so the restore drill below passed and nothing ever
looked wrong — while `psql -f`, another machine, or any other tool would have
failed on a file that is the only copy of the data. The script now has pg_dump
write inside the container and copies the file out as bytes, and it refuses to
report success if the result starts with a BOM or a null byte.

**Drill-tested (2026-09-15)**: restored a real backup into a throwaway
`jobflow_restore_test` database on the same running container (never touched the live `jobflow`
database) — 1 user, 209 jobs, 209 applications, exit 0 — before dropping the scratch database.
Done deliberately with `psql -f` and **not** through `Get-Content`, because the earlier drill
(2026-09-03) passed only thanks to that pipe: see the UTF-16 note above. A drill that exercises
the one code path that papers over the defect proves nothing. To repeat it:
```powershell
docker compose exec -T db psql -U jobflow -d postgres -c "CREATE DATABASE jobflow_restore_test;"
docker compose cp backups\jobflow_<timestamp>.sql db:/tmp/restore.sql
docker compose exec -T db psql -U jobflow -d jobflow_restore_test -v ON_ERROR_STOP=1 -f /tmp/restore.sql
docker compose exec -T db psql -U jobflow -d jobflow_restore_test -c "SELECT count(*) FROM users;"  # spot-check
docker compose exec -T db psql -U jobflow -d postgres -c "DROP DATABASE jobflow_restore_test;"
```

## Pre-commit hook

`.githooks/pre-commit` runs the backend test suite before every commit
(skips gracefully if the backend container isn't running — never blocks a
commit over Docker being off). `core.hooksPath` is a local git config, not
versioned, so **after a fresh clone run once**: `git config core.hooksPath .githooks`
(already configured on this machine). Bypass a single commit with `git commit --no-verify`.

