# JobFlow AI

Plataforma personal de búsqueda y postulación a empleo: perfil de carrera (CV maestro, con importación desde PDF), búsqueda en vivo agregada contra 6 APIs públicas sin autenticación + importación de vacantes desde URL, motor de coincidencia (match engine) híbrido, evaluador de CV, adaptación de CV, generación de cover letters, verificación de cuenta por correo, y una interfaz de decisión estilo Tinder.

Uso personal — ver el diseño conceptual completo en [`docs/DESIGN.md`](docs/DESIGN.md), el contrato de API en [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md), y cómo instalarla como app Android en [`docs/ANDROID_APP.md`](docs/ANDROID_APP.md).

## Stack

- **Frontend**: Next.js (App Router) + React + TypeScript + Tailwind CSS — responsive / PWA instalable en móvil, con un shell nativo Android opcional (Capacitor) para acceso remoto seguro vía VPN privada (WireGuard / Tailscale).
- **Backend**: FastAPI (Python 3.11, async SQLAlchemy 2.0).
- **Base de datos**: PostgreSQL con `pgvector` y `pg_trgm` (búsqueda full-text + semántica opcional).

```
japlication/
├── db/schema.sql          # esquema SQL fuente de verdad
├── docs/
│   ├── DESIGN.md           # diseño conceptual (pantallas, flujos, UX)
│   ├── API_CONTRACT.md     # contrato REST usado por frontend y backend
│   └── ANDROID_APP.md      # app Android (Capacitor) + acceso remoto seguro vía VPN privada
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

`GET /jobs/search/aggregate` combina en una sola búsqueda **6 APIs públicas que no requieren ningún tipo
de autenticación** (sin API key, sin OAuth, sin registro) — investigación completa, incluyendo por qué
Google Jobs y Upwork se removieron y por qué LinkedIn/Indeed no son una opción real para un proyecto
personal, en [`docs/PUBLIC_APIS_RESEARCH.md`](docs/PUBLIC_APIS_RESEARCH.md):

| Proveedor | Servicio | Servicio backend |
|---|---|---|
| Himalayas (default) | [himalayas.app](https://himalayas.app) | `backend/app/services/himalayas.py` |
| Arbeitnow | [arbeitnow.com](https://www.arbeitnow.com/api/job-board-api) | `backend/app/services/arbeitnow.py` |
| Remotive | [remotive.com](https://remotive.com/api/remote-jobs) | `backend/app/services/remotive.py` |
| Jobicy | [jobicy.com](https://jobicy.com/api/v2/remote-jobs) | `backend/app/services/jobicy.py` |
| RemoteJobs.org | [remotejobs.org](https://remotejobs.org/api-access) | `backend/app/services/remotejobs_org.py` |
| The Muse | [themuse.com](https://www.themuse.com/developers/api/v2) | `backend/app/services/themuse.py` |

## Notas de seguridad y veracidad

- La adaptación de CV, las cover letters y la importación de CV en PDF se generan **solo a partir de lo que ya existe** (el perfil maestro, o el propio PDF) — reformulan/enfatizan lenguaje existente, nunca inventan experiencia o habilidades no declaradas.
- Autenticación con JWT + contraseñas hasheadas (bcrypt); cada usuario solo ve sus propios datos.
- **Verificación de correo**: al registrarse se envía un enlace de confirmación (válido 24h) que el usuario debe confirmar con un clic; el login no se bloquea mientras tanto, pero un aviso en la app recuerda verificar y permite reenviar el correo.
