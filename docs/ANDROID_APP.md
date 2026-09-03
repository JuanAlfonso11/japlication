# JobFlow AI — Android app

The Android app is a thin native shell (built with [Capacitor](https://capacitorjs.com/)) that
points its WebView at your live JobFlow AI frontend — the same app you use in a browser, just
installed with its own icon and no browser chrome. It does **not** bundle a copy of the site, so
most frontend changes never require rebuilding the `.apk` — only changing the server address,
adding a native plugin, or changing the icon does.

Because of that, the app needs your JobFlow AI server to be reachable from your phone, wherever
you are. **We use a private VPN back into the home network for this — never a public port-forward
on the router.** Port-forwarding would expose the app directly to the public internet, and it
isn't hardened for that (no rate limiting, no WAF, etc.). A VPN never touches the public internet.

This setup uses a **WireGuard road-warrior server already running at home** — the phone connects
to it and can then reach the PC's LAN IP as if it were on the home Wi-Fi, from anywhere. (If you
don't have that, [Tailscale](https://tailscale.com/) is a good zero-config alternative — same
idea, different tool. Swap the LAN IP below for its MagicDNS hostname if you go that route.)

## Current configuration (already done)

- PC's LAN IP: **`10.0.0.232`** (Wi-Fi adapter, DHCP-assigned — see "If the IP changes" below).
- `.env` at the repo root: `CORS_EXTRA_ORIGINS=http://10.0.0.232:3000` and
  `NEXT_PUBLIC_API_URL=http://10.0.0.232:8000/api/v1`.
- `frontend/capacitor.config.ts`: `server.url = "http://10.0.0.232:3000"`, `cleartext: true`.
- `frontend/android/app/src/main/res/xml/network_security_config.xml`: allows plain `http://`
  **only** to `10.0.0.232` — nothing else the WebView loads can fall back to cleartext.
- Backend and frontend images are rebuilt and running with this config; `npx cap sync android` has
  been run, so the native project already has the right server URL baked in.

Verify it end-to-end from your phone before building the APK: connect to your WireGuard VPN, then
open `http://10.0.0.232:3000` in Chrome. If it loads and you can log in, the hard part is done —
the Android app below is just a wrapper around this same URL. This also already gets you a fast
path to "always available" with zero extra tooling: Chrome on Android will offer **Add to Home
Screen** on that URL (JobFlow AI ships a PWA manifest), which installs a full-screen icon. Do this
now if you don't need the native `.apk` at all.

## Remaining steps — building the `.apk`

### 1. Install a JDK + the Android SDK

Neither is installed on this machine yet. The simplest way to get both correctly configured on
Windows is to install **Android Studio** (https://developer.android.com/studio) and let its setup
wizard install the SDK + accept licenses — **you never have to open Android Studio's editor**, VS
Code stays your editor for everything; Android Studio is just the standard installer for the
SDK/build tools on Windows.

After installing, note the SDK path (Android Studio → More Actions → SDK Manager, or
`%LOCALAPPDATA%\Android\Sdk` by default) and set it once:

```powershell
setx ANDROID_HOME "$env:LOCALAPPDATA\Android\Sdk"
```

(Open a new terminal after `setx` for it to take effect.)

### 2. Build

From `frontend/android/`, in a terminal that has `ANDROID_HOME` set (PowerShell, or VS Code's
integrated terminal):

```
.\gradlew.bat assembleDebug
```

The first run downloads Gradle + dependencies (can take a while). Output APK:

```
frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

### 3. Install it on your phone

Copy `app-debug.apk` to your phone (cloud drive, USB, email, a WireGuard-reachable file share —
anything) and open it there. Android will ask to allow installs from that source once; approve it,
then install. You'll see a **JobFlow AI** icon like any other app.

## If the IP changes

`10.0.0.232` came from DHCP, so it could change after a router reboot or lease renewal. If the app
stops connecting, check the PC's current LAN IP and update it in three places, then re-sync/rebuild:

1. `.env` (`CORS_EXTRA_ORIGINS`, `NEXT_PUBLIC_API_URL`) → `docker compose build backend frontend && docker compose up -d`
2. `frontend/capacitor.config.ts` (`server.url`)
3. `frontend/android/app/src/main/res/xml/network_security_config.xml` (the `<domain>` value)

Then `npx cap sync android` and `.\gradlew.bat assembleDebug` again. To avoid this entirely, set a
DHCP reservation for this PC in your router's settings so its LAN IP never changes.

## Updating later

- **Frontend/backend code changes**: just `docker compose build && docker compose up -d` as usual
  — the Android app loads the live server, no APK rebuild needed.
- **Changing the VPN address, the app icon, or adding a native plugin**: edit
  `capacitor.config.ts` (or the relevant native file), run `npx cap sync android` (needs Node — if
  not on this machine, use
  `docker run --rm -v "${PWD}/frontend:/app" -w /app node:22 npx cap sync android` from the repo
  root, same as this setup used), then `.\gradlew.bat assembleDebug` again and reinstall.

## Notes

- `frontend/android/` is the generated native project — build output, `local.properties` (has a
  machine-specific SDK path), and any keystores are gitignored; the source/config files are
  tracked normally.
- This produces a **debug-signed** APK, fine for installing on your own device. If you ever want
  to distribute it more broadly (e.g. Play Store), it would need a proper release signing key —
  out of scope for personal use.
