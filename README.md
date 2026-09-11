# JobFlow AI

Plataforma personal de búsqueda y postulación a empleo: perfil de carrera (CV maestro, con importación desde PDF), búsqueda en vivo agregada contra 15 fuentes de empleo (LinkedIn incluido) + importación de vacantes desde URL, motor de coincidencia (match engine) híbrido, evaluador de CV, adaptación de CV, generación de cover letters, verificación de cuenta por correo, y una interfaz de decisión estilo Tinder.

Uso personal — ver el diseño conceptual completo en [`docs/DESIGN.md`](docs/DESIGN.md), el contrato de API en [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md), y cómo instalarla como app Android en [`docs/ANDROID_APP.md`](docs/ANDROID_APP.md).

## Stack

- **Frontend**: Next.js (App Router) + React + TypeScript + Tailwind CSS — responsive / PWA instalable en móvil, con un shell nativo Android opcional (Capacitor) para acceso remoto seguro vía Tailscale.
- **Backend**: FastAPI (Python 3.11, async SQLAlchemy 2.0).
- **Base de datos**: PostgreSQL con `pgvector` y `pg_trgm` (búsqueda full-text + semántica opcional).

```
japlication/
├── db/schema.sql          # esquema SQL fuente de verdad
├── docs/
│   ├── DESIGN.md           # diseño conceptual (pantallas, flujos, UX)
│   ├── API_CONTRACT.md     # contrato REST usado por frontend y backend
│   └── ANDROID_APP.md      # app Android (Capacitor) + acceso remoto seguro vía Tailscale
├── backend/                 # API FastAPI
├── frontend/                 # App Next.js (incluye frontend/android/, el proyecto nativo)
└── docker-compose.yml
```

## Puesta en marcha rápida (Docker)

```bash
cp .env.example .env
# (opcional) agrega tu ANTHROPIC_API_KEY en .env para adaptación de CV / cover letters / evaluador de
# CV / importación de PDF con IA real; sin ella, el sistema usa generadores basados en reglas y sigue
# siendo 100% funcional.
# (opcional) agrega SMTP_HOST (+ SMTP_USER/PASSWORD/...) para que el correo de verificación de cuenta
# se envíe de verdad; sin SMTP configurado, el link queda en los logs del backend y el flujo se puede
# probar igual en local.

docker compose up --build
```

- Backend: http://localhost:8000 (docs interactivas en `/docs`)
- Frontend: http://localhost:3000
- PostgreSQL: `localhost:5432` (usuario/clave `jobflow`/`jobflow`, la base `jobflow`)

El esquema (`db/schema.sql`) se aplica automáticamente al crear el volumen de Postgres la primera vez.

### Migraciones

El backend lleva el esquema al día **solo, al arrancar** (`backend/entrypoint.sh` →
`app/scripts/migrate.py`), antes de aceptar la primera petición. Si una migración falla, el
contenedor no arranca: es preferible a servir datos contra un esquema en estado desconocido.

Conviven dos formas de crear el esquema y el script las distingue:

| Estado de la base | Qué hace |
|---|---|
| Con historial de Alembic | `alembic upgrade head` |
| Con esquema pero sin historial (nació de `schema.sql`) | `alembic stamp head` — ya está al día |
| Vacía | `alembic upgrade head` desde cero (la revisión 0001 reproduce `schema.sql`) |

**La regla que sostiene esto:** `db/schema.sql` es la fuente de verdad y se mantiene en sync con el
historial de migraciones. Agregar una migración sin actualizar `schema.sql` haría que una base nueva
se estampe sin esa columna.

La base de tests (`jobflow_test`) es separada y persistente, así que se migra aparte:

```bash
docker compose run --rm backend python -m app.scripts.migrate --database jobflow_test
```

## Desarrollo local sin Docker

### 1. Base de datos

```bash
createdb jobflow
psql jobflow -f db/schema.sql
```

### 2. Backend

Ver instrucciones detalladas en [`backend/README.md`](backend/README.md). Resumen:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ajusta DATABASE_URL si no usas Docker
uvicorn app.main:app --reload
```

### 3. Frontend

Ver instrucciones detalladas en [`frontend/README.md`](frontend/README.md). Resumen:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

## Las tres funcionalidades prioritarias del MVP

1. **Career Profile (CV Maestro)** — `backend/app/services` + `frontend/app/profile`: almacena información factual del usuario; nunca se sobreescribe automáticamente, las versiones adaptadas por vacante son derivadas (`resume_versions`).
2. **Job Import** — `backend/app/services/job_importer.py`: normaliza una vacante (URL o texto) a JSON estructurado, priorizando JSON-LD (`schema.org/JobPosting`) con fallback heurístico. El mismo extractor alimenta la búsqueda en vivo.
3. **Match Engine** — `backend/app/services/match_engine.py`: score híbrido ponderado (50% técnico / 30% experiencia / 20% semántico), con skills coincidentes, faltantes y "concerns" en lenguaje natural.

## Búsqueda en vivo

`GET /jobs/search/aggregate` combina en una sola búsqueda **15 fuentes**: 12 que no requieren
ningún tipo de autenticación (sin API key, sin OAuth, sin registro; LinkedIn entre ellas, por sus
páginas públicas de empleo) y 3 con clave gratuita de registro instantáneo. Las que tienen clave se
saltan solas si no están configuradas. Los resultados se deduplican antes de devolverse
(`backend/app/services/job_dedupe.py`). Investigación completa —incluyendo por qué se descartaron
varias y cómo entra LinkedIn sin cuenta ni API— en
[`docs/PUBLIC_APIS_RESEARCH.md`](docs/PUBLIC_APIS_RESEARCH.md):

| Proveedor | Auth | Servicio backend |
|---|---|---|
| Himalayas | — | `himalayas.py` |
| Arbeitnow | — | `arbeitnow.py` |
| Remotive | — | `remotive.py` |
| Jobicy | — | `jobicy.py` |
| RemoteJobs.org | — | `remotejobs_org.py` |
| The Muse | — | `themuse.py` |
| We Work Remotely | — | `weworkremotely.py` |
| Hacker News (Who is hiring) | — | `hackernews.py` |
| Get on Board | — | `getonbrd.py` |
| Working Nomads | — | `workingnomads.py` |
| Remote OK | — | `remoteok.py` |
| LinkedIn (páginas públicas) | — | `linkedin_jobs.py` |
| Adzuna | clave gratis | `adzuna.py` |
| USAJobs | clave gratis | `usajobs.py` |
| Google Jobs (SerpApi) | clave gratis | `serpapi_jobs.py` |

Remote OK pide, en sus términos, que se enlace de vuelta a su ficha y se los nombre como fuente: por
eso su `source_url` apunta a su página y nunca al `apply_url` del empleador.

## Kit de aplicación

Los productos de "auto-apply" (JobCopilot, Sorce, Comet) no venden encontrar vacantes — venden
**dejar de retipear los mismos doce campos**. JobPilot ataca ese mismo trabajo repetitivo sin un bot
que postule por ti:

- **Respuestas frecuentes** (`Perfil → Respuestas frecuentes`): las preguntas que todo formulario
  vuelve a hacer (autorización de trabajo, preaviso, expectativa salarial). Se responden una vez y
  se guardan en `career_profiles.screening_answers`.
- **Kit por vacante** (`components/ApplicationKit.tsx`, en el detalle del trabajo): datos de
  contacto y esas respuestas, cada uno con botón de copiar, junto al enlace al formulario original.

La diferencia con el auto-apply es deliberada: esas herramientas responden preguntas de screening
en tu nombre, lo que implica inventar cosas que nunca declaraste — justo lo que el resto del sistema
evita. Acá el texto lo escribiste tú; lo único que se automatiza es no volver a escribirlo. (Además
el auto-apply es frágil: Perplexity lo lanzó y lo retiró a las pocas semanas.)

## Después de aplicar

- **Editar el CV generado** (`PATCH /resume-versions/{id}`): las versiones generadas eran de solo
  lectura, así que una viñeta mal redactada solo se arreglaba editando el PDF por fuera — y esa
  corrección se perdía. Ahora se edita en la app, y la versión editada queda marcada
  (`edited_at`), lo que además la vuelve la preferida cuando una vacante parecida busca un CV para
  reutilizar: la corrección se hace una vez y se propaga.
- **Qué te falta para subir el score** (`GET /match/skill-gaps`): agrega los `missing_skills` que el
  match engine ya guardaba, sobre las vacantes que el usuario *quiso* (guardadas, aplicadas,
  entrevistando, oferta, rechazadas). Responde "qué me sigue costando puntos", que es distinto de
  "por qué esta vacante puntuó 68".
- **Preparación de entrevista** (`POST /jobs/{id}/interview-prep`): las preguntas que esa vacante va
  a producir, con puntos de apoyo sacados de las viñetas del propio perfil. Una skill que el usuario
  *no* tiene se presenta como brecha a preparar con honestidad, nunca como una respuesta que fingir.
  Funciona sin `ANTHROPIC_API_KEY` (el generador basado en reglas es el default).

## Cuando algo falla

Todo lo que falla queda en un solo lugar consultable, `error_logs`, y se lee desde la app en
**Perfil → Análisis → Errores recientes** — sin abrir `docker compose logs` ni una laptop.

- **Errores del backend**: `ErrorLoggingMiddleware` captura cualquier excepción no manejada con su
  traceback, la ruta y el usuario, y devuelve un 500 que **incluye un código corto**. Ese mismo
  código va en la cabecera `X-Request-Id` de *toda* respuesta, así que un reporte de "me salió el
  código a1b2c3" se busca directo en vez de adivinar por hora.
- **Errores del frontend**: antes eran invisibles — un crash en el WebView del celular no dejaba
  rastro. Ahora un `ErrorBoundary` atrapa los fallos de render (con el *component stack*, que es lo
  que dice qué componente rompió) y los handlers globales atrapan el resto; todo se reporta a la
  misma tabla.

Dos decisiones deliberadas:

- **Nunca se guarda el cuerpo de la petición.** Lo primero que lleva un `POST /auth/login` es una
  contraseña; un log que la captura convierte una ayuda de diagnóstico en una filtración de
  credenciales. Se guarda de dónde vino el error y qué falló, nunca con qué datos. Hay un test que
  lo verifica.
- **Los 4xx no se registran.** Un 401 por token vencido es la app funcionando; enterrar los fallos
  reales bajo miles de esos es cómo un log deja de leerse.

Retención: 30 días, podados por `scripts/backup-db.ps1` *después* del respaldo de esa noche.

## Notas de seguridad y veracidad

- La adaptación de CV, las cover letters y la importación de CV en PDF se generan **solo a partir de lo que ya existe** (el perfil maestro, o el propio PDF) — reformulan/enfatizan lenguaje existente, nunca inventan experiencia o habilidades no declaradas.
- Autenticación con JWT + contraseñas hasheadas (bcrypt); cada usuario solo ve sus propios datos.
- **Verificación de correo**: al registrarse se envía un enlace de confirmación (válido 24h) que el usuario debe confirmar con un clic; el login no se bloquea mientras tanto, pero un aviso en la app recuerda verificar y permite reenviar el correo.
