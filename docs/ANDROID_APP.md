# JobFlow AI — Android app

The Android app is a thin native shell (built with [Capacitor](https://capacitorjs.com/)) that
points its WebView at your live JobFlow AI frontend — the same app you use in a browser, just
installed with its own icon and no browser chrome. It does **not** bundle a copy of the site, so
most frontend changes never require rebuilding the `.apk` — only changing the server address,
adding a native plugin, or changing the icon does.

Because of that, the app needs your JobFlow AI server to be reachable from your phone, wherever
you are. **We use [Tailscale Funnel](https://tailscale.com/kb/1223/funnel) for this**: it publishes
the PC's `*.ts.net` HTTPS name on the public internet, so the phone opens the app like any other
app — no VPN on the phone, no router port-forwarding, no domain to buy, free.

## Acceso público (Tailscale Funnel)

Tailscale corre **solo en la PC**. El teléfono ya no lo necesita: la URL sigue siendo
`jobpilot.tailb3d4c1.ts.net`, que ahora resuelve en internet público. Por eso la APK no cambió:
`capacitor.config.ts`, el intent-filter del manifest y `MainActivity.ALLOWED_HOST` siguen valiendo.
Con Tailscale encendido en el teléfono también funciona.

```
tailscale funnel --bg --https=443   http://localhost:3000   # frontend
tailscale funnel --bg --https=8443  http://localhost:8000   # backend
tailscale funnel --bg --https=10000 http://localhost:8446   # APK update server
tailscale funnel status                                     # los tres deben decir "Funnel on"
```

Funnel solo permite los puertos 443, 8443 y 10000; por eso el servidor de la APK pasó del 8444 al
10000 (`.env`: `ANDROID_UPDATE_APK_URL=https://jobpilot.tailb3d4c1.ts.net:10000/`). La primera vez,
Funnel se habilita en la tailnet desde el enlace que imprime el comando (atributo `funnel` en la
política de acceso).

Qué protege la app ahora que es pública:
- **Registro cerrado** tras la primera cuenta (`ALLOW_EXTRA_REGISTRATIONS`).
- **Todas las rutas de datos exigen login**. Las únicas abiertas: login/refresh/logout, verificar
  correo, `/app/android-update` (solo la versión) y `/system/heartbeat` (pide secreto).
- **Rate limit por IP real**: uvicorn con `--proxy-headers` (`backend/Dockerfile`). Los puertos de
  Docker escuchan solo en `127.0.0.1`, así que nadie salta el proxy. Tailscale reescribe
  `X-Forwarded-For`, así que una IP inventada por el cliente no se cuela (comprobado).
- **Bloqueo por cuenta**: 10 logins fallidos en 15 min cierran ese correo 15 min, venga de la IP
  que venga (`LoginLockout` en `backend/app/core/rate_limit.py`).
- **Cabeceras de seguridad**: CSP con nonce por petición en el frontend (`frontend/middleware.ts`)
  y CSP `default-src 'none'` en la API, más HSTS, `nosniff` y `frame-ancestors 'none'`. En el
  WebView de Android los scripts caen a `'unsafe-inline'` porque Capacitor inyecta su puente
  inline sin nonce.
- **`/docs` y `/openapi.json` ocultos** salvo con `ENABLE_API_DOCS=1`.
- **Contenedores sin root** y optimizador de imágenes de Next apagado.
- **Dependencias vigiladas**: `scripts/check-deps.ps1` cada semana (instalar con
  `scripts/install-deps-audit-schedule.ps1`) y `npm audit` en el pre-commit.
- **Los scripts de encendido/apagado respetan el modo**: `start-jobpilot.bat` y
  `jobpilot-control.ps1` usan `funnel` si ya está activo, para no sacar la app de internet
  al re-apuntar el 443.
- **Tu contraseña** sigue siendo la barrera principal: larga y única.

Si la PC está apagada, la app muestra `offline.html` — eso no cambia con Funnel.

## Configuración anterior (solo tailnet, antes de Funnel)

- Tailscale installed on this PC and logged in. Its MagicDNS hostname: **`jobpilot.tailb3d4c1.ts.net`**.
- **HTTPS Certificates** enabled for the tailnet (Tailscale admin console →
  [DNS settings](https://login.tailscale.com/admin/dns)), and `tailscale serve` set up to expose
  both services with a real, auto-renewing Tailscale-issued TLS cert — no manual cert files, no
  renewal cron:
  ```
  tailscale serve --bg --https=443  http://localhost:3000   # frontend
  tailscale serve --bg --https=8443 http://localhost:8000   # backend
  tailscale serve --bg --https=8444 http://localhost:8446   # APK update server
  ```
  This config lives in `tailscaled` itself (`--bg` = persists across reboots), not in this repo —
  if it's ever lost, re-run the three commands above (check current state with `tailscale serve status`).

  The third route is the one that's easy to forget, because nothing in `docker compose` creates it:
  it's set up by `scripts\install-apk-server-autostart.ps1` (which also reserves the URL ACL for
  `http://+:8446/`) and served by `scripts\apk-server\serve-apk.ps1`, a small `HttpListener` that
  hands out `scripts\apk-server\jobpilot.apk` — the file `ship-android-update.ps1` writes and
  `UpdateChecker.tsx` downloads for the in-app update banner. Two things worth knowing about it:

  - **It has no authentication.** With Funnel, anyone can `GET` the APK. That's acceptable because
    the APK contains no secrets (the app is a WebView shell; every credential lives behind the
    backend's login).
  - **It runs outside Docker**, as a login-time scheduled task. If the update banner ever says a
    new version exists but the download fails, check that process first (`Get-Process powershell`,
    or just re-run `install-apk-server-autostart.ps1`); the containers being healthy says nothing
    about it.
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

## Onboarding beta testers (people outside your own devices)

The setup above assumes every device is logged into **the same Tailscale account** (yours). For an
external tester, don't invite them as a full tailnet member — that would give them visibility into
your other devices too. Instead, share just the `jobpilot` node:

1. In the [admin console → Machines](https://login.tailscale.com/admin/machines), find `jobpilot` →
   `···` menu → **Share...** → enter the tester's email. This gives them access to only that node,
   appearing as a shared machine in their own tailnet — not membership in yours.
2. Tailscale emails them an invite automatically.

What to send the tester:

1. Accept the Tailscale share invite email.
2. Install Tailscale (`https://tailscale.com/download`, or the Play Store on Android) and sign in
   with the invited email.
3. With Tailscale connected, open `https://jobpilot.tailb3d4c1.ts.net` in Chrome and log in. From
   there, **Add to Home Screen** (PWA) is the easiest way for them to get an app icon — avoids
   walking each tester through sideloading the unsigned debug `.apk`.

## About the earlier WireGuard attempt

This setup originally targeted a self-hosted WireGuard road-warrior server, but that needed router
admin access (port forwarding, master keys) that wasn't available. Tailscale avoids that entirely
— it's a fine substitute and, if you ever get WireGuard sorted out later, either works equally
well; there's no need to revisit this unless Tailscale itself becomes unavailable.

## Firma: debug hoy, release listo para cuando quieras

El APK que se publica hoy va **firmado en modo debug**, que funciona bien para sideload. Lo que no
es obvio: eso ya depende de un keystore que nadie gestiona (`~/.android/debug.keystore`, con la
contraseña pública `android`). Si se pierde o se regenera, ninguna instalación existente se puede
actualizar nunca más. O sea que el riesgo de "perder la clave" ya existe — solo que invisible.

Por eso hay una clave de release preparada:

```powershell
.\scripts\create-release-keystore.ps1          # una sola vez, ya ejecutado
.\scripts\ship-android-update.ps1 -Notes "..." -Release
```

`app/build.gradle` la usa solo si `android/keystore.properties` existe; si no, cae al debug, para
que un clon fresco siga compilando.

**El cambio de firma es de una sola vez y coordinado.** Android rechaza instalar un APK cuya firma
difiera de la instalada, así que el primer build de release **no puede actualizar a nadie**: cada
dispositivo (el tuyo y el de cada tester) tiene que desinstalar JobPilot e instalar de nuevo. No se
pierde nada — todo el estado vive en el servidor — pero es un paso a coordinar, no algo con lo que
tropezar. Por eso `-Release` no es el default.

**Respalda fuera de esta PC** `frontend/android/keystore/jobpilot-release.keystore` y
`frontend/android/keystore.properties`. Ambos están gitignored; perderlos significa no poder
actualizar nunca más sobre las instalaciones existentes.

## Notes

- `frontend/android/` is the generated native project — build output, `local.properties` (has a
  machine-specific SDK path), and any keystores are gitignored; the source/config files are
  tracked normally.
- Node **sí** está instalado en esta máquina (`C:\Program Files\nodejs`), que es lo que usa
  `scripts/ship-android-update.ps1` para `npx cap sync`. La nota anterior decía lo contrario y
  recomendaba Docker para eso; quedó desactualizada.
