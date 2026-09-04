# JobFlow AI — Android app

The Android app is a thin native shell (built with [Capacitor](https://capacitorjs.com/)) that
points its WebView at your live JobFlow AI frontend — the same app you use in a browser, just
installed with its own icon and no browser chrome. It does **not** bundle a copy of the site, so
most frontend changes never require rebuilding the `.apk` — only changing the server address,
adding a native plugin, or changing the icon does.

Because of that, the app needs your JobFlow AI server to be reachable from your phone, wherever
you are. **We use [Tailscale](https://tailscale.com/) for this — a private, encrypted VPN mesh
between only your own devices — instead of opening any port on your home router.**
Port-forwarding would expose the app directly to the public internet, and it isn't hardened for
that (no rate limiting, no WAF, etc.). Tailscale traffic never touches the public internet at all,
and unlike a self-hosted WireGuard road-warrior server, it needs **zero router configuration** —
no port forwarding, no admin/master keys — which is why we switched to it after running into
trouble getting router access for WireGuard.

## Current configuration (already done)

- Tailscale installed on this PC and logged in. Its MagicDNS hostname: **`jobpilot.tailb3d4c1.ts.net`**.
- **HTTPS Certificates** enabled for the tailnet (Tailscale admin console →
  [DNS settings](https://login.tailscale.com/admin/dns)), and `tailscale serve` set up to expose
  both services with a real, auto-renewing Tailscale-issued TLS cert — no manual cert files, no
  renewal cron:
  ```
  tailscale serve --bg --https=443  http://localhost:3000   # frontend
  tailscale serve --bg --https=8443 http://localhost:8000   # backend
  ```
  This config lives in `tailscaled` itself (`--bg` = persists across reboots), not in this repo —
  if it's ever lost, re-run the two commands above (check current state with `tailscale serve status`).
- `.env` at the repo root: `FRONTEND_ORIGIN=https://jobpilot.tailb3d4c1.ts.net`,
  `BACKEND_PUBLIC_URL` and `NEXT_PUBLIC_API_URL` both
  `https://jobpilot.tailb3d4c1.ts.net:8443/api/v1`.
- `frontend/capacitor.config.ts`: `server.url = "https://jobpilot.tailb3d4c1.ts.net"` — no
  `cleartext` flag anymore, it's real HTTPS end to end.
- No `network_security_config.xml` needed anymore (removed) — the WebView only ever talks HTTPS
  now, which is Android's secure default with no exceptions required.
- Backend and frontend images are rebuilt and running with this config, verified reachable over
  the Tailscale hostname; `npx cap sync android` has been run, so the native project already has
  the right server URL baked in.

## 1. Install Tailscale on your phone

1. Install **Tailscale** from the Play Store.
2. Sign in with the **same account** used on the PC.
3. That's it — no server setup, no keys to exchange. Both devices show up automatically in your
   [Tailscale admin console](https://login.tailscale.com/admin/machines) once both are logged in.

Verify it end-to-end before building the APK: with Tailscale connected on the phone (its toggle
"on" in the Tailscale app — works over Wi-Fi or mobile data, anywhere), open
`https://jobpilot.tailb3d4c1.ts.net` in Chrome. If it loads and you can log in, the hard part
is done — the Android app below is just a wrapper around this same URL. This also already gets you
a fast path to "always available" with zero extra tooling: Chrome on Android will offer **Add to
Home Screen** on that URL (JobFlow AI ships a PWA manifest), which installs a full-screen icon. Do
this now if you don't need the native `.apk` at all.

## Building the `.apk` — done, and how it was set up

Already installed and working on this machine:

- **Android Studio** (via `winget install Google.AndroidStudio`) — installed purely as the
  standard way to get licensed SDK components on Windows. You never need to open its editor; VS
  Code stays your editor for everything.
- **Android SDK** at `%LOCALAPPDATA%\Android\Sdk` — `platform-tools`, `platforms;android-36`,
  `build-tools;36.0.0` (installed headlessly via `cmdline-tools`' `sdkmanager`, licenses
  pre-accepted). `ANDROID_HOME` is set to this path (`setx`, persists across new terminals).
- **Eclipse Temurin JDK 21** (via `winget install EclipseAdoptium.Temurin.21.JDK`) — **this is the
  JDK Gradle actually needs to build with**, not Android Studio's bundled JBR. Two things bit us
  getting here, worth knowing if a rebuild ever breaks:
  - Android Studio's bundled JBR is JDK 25, too new for Gradle 8.14.3 (`Unsupported class file
    major version 69`).
  - Temurin 17 is too *old* — Capacitor 8's Android module targets Java 21 (`invalid source
    release: 21`).
  - JDK 21 is the one that actually works.

To build (or rebuild after a config/plugin change), from `frontend/android/` in PowerShell or VS
Code's integrated terminal:

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot"
.\gradlew.bat assembleDebug
```

(`ANDROID_HOME` is already set persistently via `setx`, so it doesn't need to be repeated per
session — but `JAVA_HOME` as set above is only for that terminal session; set it again in any new
terminal you build from, or set it permanently the same way: `setx JAVA_HOME "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot"`.)

The first run downloads Gradle + dependencies (can take a while). Output APK:

```
frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

### Install it on your phone

Copy `app-debug.apk` to your phone (Tailscale file share via Taildrop, a cloud drive, USB, email —
anything) and open it there. Android will ask to allow installs from that source once; approve it,
then install. You'll see a **JobFlow AI** icon like any other app.

## Updating later

- **Frontend/backend code changes**: just `docker compose build && docker compose up -d` as usual
  — the Android app loads the live server, no APK rebuild needed.
- **Changing the Tailscale hostname, the app icon, or adding a native plugin**: edit
  `capacitor.config.ts` (or the relevant native file), run `npx cap sync android` (needs Node — if
  not on this machine, use
  `docker run --rm -v "${PWD}/frontend:/app" -w /app node:22 npx cap sync android` from the repo
  root, same as this setup used), then `.\gradlew.bat assembleDebug` again and reinstall.

## About the earlier WireGuard attempt

This setup originally targeted a self-hosted WireGuard road-warrior server, but that needed router
admin access (port forwarding, master keys) that wasn't available. Tailscale avoids that entirely
— it's a fine substitute and, if you ever get WireGuard sorted out later, either works equally
well; there's no need to revisit this unless Tailscale itself becomes unavailable.

## Notes

- `frontend/android/` is the generated native project — build output, `local.properties` (has a
  machine-specific SDK path), and any keystores are gitignored; the source/config files are
  tracked normally.
- This produces a **debug-signed** APK, fine for installing on your own device. If you ever want
  to distribute it more broadly (e.g. Play Store), it would need a proper release signing key —
  out of scope for personal use.
