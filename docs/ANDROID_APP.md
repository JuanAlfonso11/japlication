# JobFlow AI — Android app

The Android app is a thin native shell (built with [Capacitor](https://capacitorjs.com/)) that
points its WebView at your live JobFlow AI frontend — the same app you use in a browser, just
installed with its own icon and no browser chrome. It does **not** bundle a copy of the site, so
most frontend changes never require rebuilding the `.apk` — only changing the server address,
adding a native plugin, or changing the icon does.

Because of that, the app needs your JobFlow AI server to be reachable from your phone, wherever
you are. **We use [Tailscale](https://tailscale.com/) for this — a private, encrypted VPN between
only your own devices — instead of opening any port on your home router.** Port-forwarding would
expose the app directly to the public internet, and it isn't hardened for that (no rate limiting,
no WAF, etc.). Tailscale traffic never touches the public internet at all.

## 1. Install Tailscale

1. On your PC: install [Tailscale for Windows](https://tailscale.com/download/windows), sign in
   (any provider — Google/Microsoft/GitHub all work), and leave it running.
2. On your phone: install **Tailscale** from the Play Store, sign in with the **same account**.
3. Both devices now show up in your [Tailscale admin console](https://login.tailscale.com/admin/machines).
   Click your PC's entry and copy its **MagicDNS name** — looks like
   `your-pc-name.tailXXXXX.ts.net`. That's the hostname you'll use everywhere below instead of
   `localhost`.

   (If MagicDNS is off, enable it in the admin console under DNS settings — it's on by default for
   new tailnets.)

## 2. Point the backend and frontend at your Tailscale hostname

Edit (or create) `.env` at the repo root:

```
FRONTEND_ORIGIN=http://localhost:3000
CORS_EXTRA_ORIGINS=http://your-pc-name.tailXXXXX.ts.net:3000
NEXT_PUBLIC_API_URL=http://your-pc-name.tailXXXXX.ts.net:8000/api/v1
```

- `CORS_EXTRA_ORIGINS` lets the backend accept requests from the phone/Android app's origin, on
  top of your local `localhost:3000` dev origin (comma-separate more origins if you ever need to).
- `NEXT_PUBLIC_API_URL` is baked into the frontend's JS at **build time** — it's what every
  browser tab or the Android app will call, so it has to be an address *they* can reach, not
  `localhost` (which on the phone would mean the phone itself).

Then rebuild both:

```
docker compose build backend frontend
docker compose up -d
```

Confirm it works from your phone first, in Chrome, before touching the Android app: open
`http://your-pc-name.tailXXXXX.ts.net:3000` with Tailscale running on the phone. If that loads and
you can log in, the hard part is done — the Android app below is just a wrapper around this same
URL. This also already gets you a fast path to "always available": Chrome on Android will offer
**Add to Home Screen** on that URL (JobFlow AI already ships a PWA manifest), which installs a
full-screen icon with zero extra tooling. Do this now if you don't want the native `.apk` at all —
skip straight to done.

## 3. Point the Android app at the same hostname

Edit `frontend/capacitor.config.ts`:

```ts
server: {
  url: "http://your-pc-name.tailXXXXX.ts.net:3000",
  cleartext: true,
},
```

`cleartext: true` is what allows `http://` (not `https://`) here — safe specifically because
Tailscale already encrypts everything between your devices at the VPN layer. The native project's
`network_security_config.xml` only allows cleartext to `*.ts.net` hosts, so this can't silently
apply to some other, non-Tailscale address later.

Then sync the native project (from `frontend/`, needs Node — see prerequisites below):

```
npx cap sync android
```

## 4. Prerequisites to build the `.apk`

You need a JDK and the Android SDK — these aren't installed on this machine yet. The simplest way
to get both correctly configured on Windows is to install **Android Studio**
(https://developer.android.com/studio) and let its setup wizard install the SDK + accept licenses
— **you never have to open Android Studio's editor**, VS Code stays your editor for everything,
Android Studio is just the standard installer for the SDK/build tools on Windows.

After installing, note the SDK path it used (Android Studio → More Actions → SDK Manager, or
`%LOCALAPPDATA%\Android\Sdk` by default) and set it once:

```powershell
setx ANDROID_HOME "$env:LOCALAPPDATA\Android\Sdk"
```

(Open a new terminal after `setx` for it to take effect.)

Node is also needed for `npx cap` commands — if you don't have it on the host, run them the same
way this setup did, via an ephemeral Docker container with the frontend folder mounted:

```
docker run --rm -v "${PWD}/frontend:/app" -w /app node:22 npx cap sync android
```

## 5. Build the `.apk`

From `frontend/android/` in a terminal that has `ANDROID_HOME` set (PowerShell, or VS Code's
integrated terminal):

```
.\gradlew.bat assembleDebug
```

The first run downloads Gradle + dependencies (can take a while). Output APK:

```
frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

## 6. Install it on your phone

Copy `app-debug.apk` to your phone (Tailscale file share, a cloud drive, USB, email — anything)
and open it there. Android will ask to allow installs from that source once; approve it, then
install. You'll see a **JobFlow AI** icon like any other app.

## Updating later

- **Frontend/backend code changes**: just `docker compose build && docker compose up -d` as usual
  — the Android app loads the live server, no APK rebuild needed.
- **Changing the Tailscale hostname, the app icon, or adding a native plugin**: edit
  `capacitor.config.ts` (or the relevant native file), run `npx cap sync android`, then
  `.\gradlew.bat assembleDebug` again and reinstall.

## Notes

- `frontend/android/` is the generated native project — build output, `local.properties` (has a
  machine-specific SDK path), and any keystores are gitignored; the source/config files are
  tracked normally.
- This produces a **debug-signed** APK, fine for installing on your own device. If you ever want
  to distribute it more broadly (e.g. Play Store), it would need a proper release signing key —
  out of scope for personal use.
