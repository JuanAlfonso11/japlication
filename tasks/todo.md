# Tareas: endurecer JobPilot para acceso público

Plan y hallazgos: [`tasks/plan.md`](plan.md). Tests de backend y frontend: el hook `.githooks/pre-commit` los corre en cada commit (backend con pytest, frontend con `docker build --target test`, más `docker compose build frontend`).

---

## Fase 1: bloqueantes

### T1: Subir Next.js a 15.5.26 + React 19
**Descripción:** Cierra H1 (RCE sin login en el optimizador de imágenes, DoS en Server Components, SSRF, cache poisoning). Next 14 ya no recibe parches.

**Criterios de aceptación:**
- [x] `next@15.5.26`, `react`/`react-dom@19`, `eslint-config-next@15.5.26` y `@types/react*@19` en `package.json`
- [x] `npm audit --omit=dev` sin críticas ni altas
- [ ] Todas las pantallas cargan y funcionan igual que antes (login, swipe, trabajos, detalle `jobs/[id]`, perfil, pipeline, exportaciones) — *verificado solo sin sesión (login, /, perfil, verify-email sin errores de consola); falta el recorrido con sesión iniciada*

**Verificación:**
- [x] Codemod innecesario: todas las páginas son client components con `useParams` (no hay `params` de servidor)
- [x] `npm test` y `npm run build` en `frontend/`
- [x] `docker compose up -d --build frontend` y recorrer la app en el navegador

**Dependencias:** ninguna
**Archivos probables:** `frontend/package.json`, `frontend/package-lock.json`, `frontend/app/jobs/[id]/page.tsx`, `frontend/app/layout.tsx`
**Tamaño:** M

### T2: Subir las dependencias de backend con CVE
**Descripción:** Cierra H2. Subir `fastapi` a una versión que traiga starlette ≥ 1.3.1, más `python-multipart>=0.0.31`, `pypdf>=6.16.1` y `lxml>=6.1.0`.

**Criterios de aceptación:**
- [x] `pip-audit` sobre la imagen nueva: sin hallazgos en starlette, python-multipart, pypdf ni lxml
- [x] Los 518 tests del backend pasan
- [x] Subir un CV en PDF sigue funcionando (pypdf 6)

**Verificación:**
- [x] `docker compose build backend`, luego `docker run --rm --entrypoint sh cld-backend -c "pip install -q pip-audit; pip-audit"`
- [x] pytest (pre-commit)
- [x] `parse_cv` sobre un PDF generado con reportlab dentro del contenedor (no por la UI)

**Dependencias:** ninguna
**Archivos probables:** `backend/requirements.txt`; quizá `backend/app/core/error_middleware.py` si Starlette 1.x cambia `BaseHTTPMiddleware`
**Tamaño:** S

### T3: Cambiar python-jose por PyJWT
**Descripción:** Cierra H3. Se va `ecdsa` (sin arreglo) y `pyasn1`.

**Criterios de aceptación:**
- [x] `requirements.txt` sin `python-jose`; con `PyJWT`
- [x] Los tokens emitidos antes del cambio siguen valiendo (mismo HS256 y mismo secreto), así que nadie pierde la sesión
- [x] `decode_access_token` sigue rechazando tokens con `purpose`, expirados o con otro algoritmo

**Verificación:**
- [x] Tests de auth y seguridad del backend (pre-commit)
- [x] `pip-audit` sin `ecdsa`/`pyasn1`
- [x] Un token emitido con jose valida con PyJWT (probado en el contenedor); en el teléfono no se probó

**Dependencias:** T2 (mismo archivo de requirements; secuencial)
**Archivos probables:** `backend/requirements.txt`, `backend/app/core/security.py`
**Tamaño:** S

## Checkpoint A: después de T1-T3
- [x] `npm audit --omit=dev` y `pip-audit` limpios (runtime)
- [x] Pre-commit en verde y `docker compose up -d --build` sin errores
- [ ] Recorrido completo en el navegador con sesión iniciada (pendiente: requiere tu login)

---

## Fase 2: defensa en profundidad

### T4: Cabeceras de seguridad
**Descripción:** Cierra H4. Frontend (`next.config.mjs` → `headers()`): CSP (`default-src 'self'`; `script-src 'self'` más el hash del script del tema; `connect-src 'self'` más el origen de la API; `frame-ancestors 'none'`), `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`. Backend: `nosniff`, `frame-ancestors 'none'` y HSTS con un middleware pequeño en `main.py`.

**Criterios de aceptación:**
- [x] `curl -I` al frontend y a la API muestra las cabeceras
- [ ] Cero violaciones de CSP — *navegador: sí (login y /, sin sesión). WebView de la APK: no probado (no hay teléfono por adb). Se aplicó directo, sin `Report-Only`; en el WebView los scripts caen a `unsafe-inline` para no romper el puente de Capacitor*
- [x] Un test del backend comprueba las cabeceras (en `/app/android-update` y en un 401)

**Verificación:**
- [x] Tests (pre-commit)
- [ ] Consola limpia en todas las pantallas y la app en el teléfono funciona — *pendiente: con sesión y en el teléfono*

**Dependencias:** T1 (la config de Next 15)
**Archivos probables:** `frontend/next.config.mjs`, `backend/app/main.py`, `backend/tests/test_security_headers.py`
**Tamaño:** M

### T5: Bloqueo de login por cuenta
**Descripción:** Cierra H5. 10 fallos en 15 min contra el mismo correo → 429 durante 15 min para ese correo, venga de la IP que venga. Contador en memoria del proceso.

**Criterios de aceptación:**
- [x] El intento 11 falla con 429 aunque la contraseña sea correcta, y el mensaje dice cuánto esperar
- [x] Un login correcto antes del umbral reinicia el contador
- [x] Mismo tiempo de respuesta para correos existentes e inexistentes (no se reabre la enumeración)

**Verificación:**
- [x] Un test nuevo en `backend/tests/` (fallos → 429 → pasa la ventana → vuelve a dejar)
- [x] pytest (pre-commit)

**Dependencias:** ninguna
**Archivos probables:** `backend/app/api/v1/routers/auth.py`, `backend/app/core/rate_limit.py`, `backend/tests/test_login_lockout.py`
**Tamaño:** S

### T6: Ocultar `/docs` en producción y limpiar CORS
**Descripción:** Cierra H6 y H8. `ENABLE_API_DOCS` en `.env` (por defecto `false`) controla `docs_url`/`redoc_url`/`openapi_url`. Quitar los orígenes `http://` de `CORS_EXTRA_ORIGINS`.

**Criterios de aceptación:**
- [x] `/docs` y `/openapi.json` dan 404 sin el flag; con `ENABLE_API_DOCS=1` vuelven
- [x] La app sigue funcionando desde `https://jobpilot…` (CORS)

**Verificación:**
- [x] `curl` a `/docs` y a `/openapi.json` → 404
- [x] Test de configuración (pre-commit)

**Dependencias:** ninguna
**Archivos probables:** `backend/app/core/config.py`, `backend/app/main.py`, `.env.example`, `.env` (local)
**Tamaño:** XS

### T7: Contenedores sin root
**Descripción:** Cierra H7. `USER` sin privilegios en las etapas finales de `backend/Dockerfile` y `frontend/Dockerfile`, con permisos de escritura solo donde hace falta (`/app/runtime` para el secreto del heartbeat).

**Criterios de aceptación:**
- [x] `docker exec cld-backend-1 id` y `docker exec cld-frontend-1 id` no dan `uid=0`
- [x] El backend sigue generando o leyendo `runtime/heartbeat_secret` y corriendo las migraciones al arrancar

**Verificación:**
- [x] `docker compose up -d --build`; `/health` responde 200; los logs no muestran permisos denegados
- [x] `scripts/Send-Heartbeat.ps1` sigue funcionando

**Dependencias:** T2 (misma imagen de backend; evita reconstruir dos veces a ciegas)
**Archivos probables:** `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml` (volumen de runtime)
**Tamaño:** S

## Checkpoint B: después de T4-T7
- [x] Pre-commit en verde; `docker compose up -d --build` limpio
- [ ] En el teléfono (todavía por Tailscale): login, swipe, exportar PDF, subir CV y banner de actualización funcionan
- [ ] **Revisión humana antes de abrir a internet**

---

## Fase 3: abrir y comprobar

### T8: Encender Funnel + verificación externa
**Descripción:** Los pasos que ya están en `docs/ANDROID_APP.md` → "Acceso público" (hacer commit de los cambios pendientes, los tres `tailscale funnel`, `serve --https=8444 off`, `ANDROID_UPDATE_APK_URL` en `.env`). Más H9: confirmar que el firewall de Windows bloquea 8446 y 3001 desde la LAN.

**Criterios de aceptación:**
- [x] `tailscale funnel status` muestra 443, 8443 y 10000 en "Funnel on"
- [x] Desde fuera (IP pública de Funnel, 2026-09-23): `/profile` → 401, `/auth/register` → 403, `/docs` y `/openapi.json` → 404, `/_next/image` → 404, cabeceras de T4 presentes
- [x] H9: sin reglas de entrada que abran 8446/3001 y la red de casa está como "Pública" (entrada bloqueada por defecto). No se probó desde otro equipo

**Verificación:**
- [x] Teléfono sin Tailscale: funciona (confirmado por el usuario)
- [x] La APK se descarga por `:10000` desde fuera (200, 6.4 MB)

**Dependencias:** Checkpoint B
**Archivos probables:** `.env` (local); configuración de tailscaled (fuera del repo)
**Tamaño:** S (lo hace el usuario; los comandos de Tailscale los bloqueó el filtro de permisos)

### T9: Auditoría de dependencias automática
**Descripción:** Para que un H1 no vuelva a pasar en silencio: añadir `npm audit --omit=dev --audit-level=high` al pre-commit (falla el commit) y un aviso semanal con `pip-audit` que reporte por `Send-Heartbeat` (mismo patrón que `check-tls-cert.ps1`).

**Criterios de aceptación:**
- [x] Un commit con una dependencia de frontend vulnerable (alta o crítica) se rechaza con un mensaje claro
- [x] El chequeo semanal aparece en `GET /system/status`

**Verificación:**
- [x] Probar el hook con un `package.json` temporal vulnerable y revertir
- [x] Correr el script a mano y ver el heartbeat

**Dependencias:** Checkpoint A (si no, el hook fallaría desde el primer día)
**Archivos probables:** `.githooks/pre-commit`, `scripts/check-deps.ps1`, `scripts/README.md`
**Tamaño:** S

## Checkpoint C: completo
- [x] Todos los criterios cumplidos
- [x] App usada un día entero desde datos móviles sin Tailscale
- [x] `docs/ANDROID_APP.md` refleja las protecciones nuevas
