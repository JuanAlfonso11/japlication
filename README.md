# JobFlow AI

Plataforma personal de búsqueda y postulación a empleo: perfil de carrera (CV maestro), importación de vacantes desde URL, motor de coincidencia (match engine) híbrido, adaptación de CV, generación de cover letters, y una interfaz de decisión estilo Tinder.

Uso personal — ver el diseño conceptual completo en [`docs/DESIGN.md`](docs/DESIGN.md) y el contrato de API en [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).

## Stack

- **Frontend**: Next.js (App Router) + React + TypeScript + Tailwind CSS — responsive / PWA instalable en móvil.
- **Backend**: FastAPI (Python 3.11, async SQLAlchemy 2.0).
- **Base de datos**: PostgreSQL con `pgvector` y `pg_trgm` (búsqueda full-text + semántica opcional).

```
japlication/
├── db/schema.sql          # esquema SQL fuente de verdad
├── docs/
│   ├── DESIGN.md           # diseño conceptual (pantallas, flujos, UX)
│   └── API_CONTRACT.md     # contrato REST usado por frontend y backend
├── backend/                 # API FastAPI
├── frontend/                 # App Next.js
└── docker-compose.yml
```

## Puesta en marcha rápida (Docker)

```bash
cp .env.example .env
# (opcional) agrega tu ANTHROPIC_API_KEY en .env para adaptación de CV / cover letters con IA real;
# sin ella, el sistema usa generadores basados en reglas y sigue siendo 100% funcional.

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
2. **URL Job Import** — `backend/app/services/job_importer.py`: normaliza una vacante (URL o texto) a JSON estructurado, priorizando JSON-LD (`schema.org/JobPosting`) con fallback heurístico.
3. **Match Engine** — `backend/app/services/match_engine.py`: score híbrido ponderado (50% técnico / 30% experiencia / 20% semántico), con skills coincidentes, faltantes y "concerns" en lenguaje natural.

## Notas de seguridad y veracidad

- La adaptación de CV y las cover letters se generan **solo a partir del perfil maestro del usuario** — reformulan/enfatizan lenguaje existente, nunca inventan experiencia o habilidades no declaradas.
- Autenticación con JWT + contraseñas hasheadas (bcrypt); cada usuario solo ve sus propios datos.
