# Plan de implementación: endurecer JobPilot antes de abrirlo a internet

## Resumen
JobPilot va a pasar de "solo mi tailnet" a público con Tailscale Funnel. La base ya está bastante endurecida: registro cerrado, todas las rutas de datos con login, JWT con lista de algoritmos y separación por propósito, refresh tokens rotados con detección de reuso, login sin oráculo de tiempo, `url_guard` contra SSRF, subida de CV con tope de tamaño leído por trozos, límite de peticiones por IP real (comprobado: Tailscale reescribe `X-Forwarded-For`, así que una IP falsa no se cuela). Este plan cierra lo que **falta**, ordenado por gravedad. **Funnel no se enciende hasta cerrar la Fase 1.**

## Hallazgos de la investigación (2026-09-23)

| # | Hallazgo | Gravedad | Evidencia |
|---|---|---|---|
| H1 | Next.js 14.2.35 sin soporte: 2 críticas (RCE sin login en el optimizador de imágenes con AVIF; la otra es solo para servidores Windows, no aplica en Docker/Linux), más varias altas de DoS en Server Components, SSRF y cache poisoning. Arreglado en 15.5.24+ | **Crítica** | `npm audit --omit=dev`: 1 crítica, 1 alta |
| H2 | Dependencias de backend con CVEs: starlette 0.41.3 (hasta 1.3.1), python-multipart 0.0.17 (hasta 0.0.31, parser de subidas), pypdf 5.1.0 (hasta 6.16.1, PDFs maliciosos), lxml 5.3.0 (hasta 6.1.0) | Alta | `pip-audit` sobre la imagen `cld-backend` |
| H3 | `python-jose` arrastra `ecdsa` (sin arreglo) y `pyasn1` viejo. Hoy no se usan (HS256), pero la librería está casi abandonada | Media | `pip-audit` |
| H4 | Sin cabeceras de seguridad (CSP, HSTS, frame-ancestors, nosniff) ni en el frontend ni en el backend. Importa porque los tokens viven en `localStorage`: un XSS se lleva la sesión | Media | `next.config.mjs` vacío; `main.py` sin middleware de cabeceras |
| H5 | El límite de login es solo por IP: un ataque desde muchas IPs contra tu correo no se frena | Media | `auth.py` `/login` `@limiter.limit("10/minute")` |
| H6 | `/docs` y `/openapi.json` públicos: exponen el mapa completo de la API | Baja | FastAPI por defecto |
| H7 | Los contenedores corren como root | Baja | Sin `USER` en ningún Dockerfile |
| H8 | CORS acepta orígenes `http://` locales (`localhost:3000`, `10.0.0.232:3000`) | Baja | `.env` `CORS_EXTRA_ORIGINS` |
| H9 | Los servidores de la APK y de la página offline escuchan en todas las interfaces (`http://+:8446`, `:3001`): accesibles desde la LAN si el firewall lo permite | Baja | `serve-apk.ps1`, `serve-offline.ps1` |

Descartados después de revisarlos: rutas sin login (probadas en vivo, todas dan 401 salvo las públicas a propósito), SSRF en la importación por URL (ya hay guard), enumeración de cuentas por registro (el registro está cerrado), inyección en el correo de postulación (requiere login y usa una huella de la vista previa), XSS por `dangerouslySetInnerHTML` (solo el script fijo del tema).

## Decisiones de arquitectura
- **Next 15.5.26 (rama backport), no 16.** Es el salto más corto que arregla todo H1. Next 15 con App Router exige React 19. Next 16 añade otro salto mayor sin beneficio de seguridad extra.
- **PyJWT en lugar de python-jose.** Misma API para HS256, mantenido y sin `ecdsa`. El cambio queda contenido en `app/core/security.py`.
- **Bloqueo por cuenta en memoria del proceso** (ventana de 15 min, 10 fallos). Un solo proceso uvicorn y un solo usuario no justifican una tabla nueva. `# ponytail:` se reinicia al reiniciar el contenedor; pasar a una columna en DB si algún día hay varios workers.
- **CSP con nonce por petición** (`frontend/middleware.ts`), porque Next mete muchos scripts inline propios; en el WebView de Android los scripts caen a `unsafe-inline` porque Capacitor inyecta su puente inline sin nonce.
- **2FA (TOTP) queda fuera**: ver Preguntas abiertas.

## Lista de tareas
Detalle y criterios en [`tasks/todo.md`](todo.md).

### Fase 1: bloqueantes (antes de Funnel)
- [x] T1: Subir Next.js a 15.5.26 + React 19 (H1)
- [x] T2: Subir las dependencias de backend con CVE (H2)
- [x] T3: Cambiar python-jose por PyJWT (H3)

### Checkpoint A
- [x] `npm audit --omit=dev` sin críticas ni altas; `pip-audit` sin hallazgos en paquetes de runtime
- [ ] Tests de backend y frontend en verde, `docker compose build` limpio, la app se usa de punta a punta en el navegador

### Fase 2: defensa en profundidad
- [x] T4: Cabeceras de seguridad en frontend y backend (H4)
- [x] T5: Bloqueo de login por cuenta (H5)
- [x] T6: Ocultar `/docs` en producción y limpiar CORS (H6, H8)
- [x] T7: Contenedores sin root (H7)

### Checkpoint B
- [ ] Tests en verde; la app en el teléfono (Tailscale todavía) funciona: login, swipe, exportar PDF, subir CV
- [ ] Revisión humana antes de abrir

### Fase 3: abrir y comprobar
- [x] T8: Encender Funnel + verificación externa (incluye H9)
- [x] T9: Auditoría de dependencias automática en el pre-commit

### Checkpoint C
- [ ] El teléfono con datos móviles y Tailscale apagado funciona; todas las comprobaciones externas de T8 pasan

## Riesgos y mitigaciones
| Riesgo | Impacto | Mitigación |
|---|---|---|
| Next 15 rompe cosas: `params`/`searchParams` pasan a ser async, cambia el caché por defecto de `fetch`, React 19 | Alto | T1 va primero y sola; el codemod `npx @next/codemod@latest upgrade`; smoke test de todas las pantallas |
| Librerías de UI (framer-motion 11) incompatibles con React 19 | Medio | Subir framer-motion a 12 si `npm i` avisa de peer deps |
| Starlette 1.x rompe algún middleware propio (`ErrorLoggingMiddleware`) | Medio | T2 corre los 518 tests; revisar el changelog de BaseHTTPMiddleware |
| Una CSP estricta rompe el WebView (Capacitor inyecta scripts) | Medio | Empezar con `Content-Security-Policy-Report-Only` un día, mirar la consola, luego aplicarla |
| El bloqueo por cuenta te deja fuera a ti | Bajo | Solo 15 min; el mensaje lo dice; `docker compose restart backend` lo borra |

## Preguntas abiertas
- **¿Quieres 2FA (TOTP con Google Authenticator/Aegis)?** Es la mejor defensa si alguien consigue tu contraseña, pero son varias pantallas y flujos (alta, códigos de respaldo). Propuesta: después de este plan, como tarea aparte.
- **¿Aviso push cuando alguien inicia sesión desde una IP nueva?** Es barato (ya existe `push_notifications.py`). Fuera de este plan salvo que lo pidas.
