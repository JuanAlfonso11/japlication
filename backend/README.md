# JobFlow AI — Backend

FastAPI backend for JobFlow AI, a personal job-search / application assistant.

## Stack

- Python 3.11, FastAPI, SQLAlchemy 2.0 (async, asyncpg), Pydantic v2, Alembic
- PostgreSQL (schema defined in `../db/schema.sql`, the source of truth)
- Optional: Anthropic API (`claude-sonnet-5`) for AI-powered resume tailoring,
  cover letters, and job parsing upgrades — every one of these features has a
  fully-functional deterministic/offline fallback when no API key is set.
- Optional: live job search — Himalayas (no key needed), Google Jobs via
  SerpApi (`SERPAPI_API_KEY`), Upwork (OAuth2, `UPWORK_CLIENT_ID`/`_SECRET`).
  See "Live job search" below.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set DATABASE_URL, JWT_SECRET, FRONTEND_ORIGIN, and (optionally)
# ANTHROPIC_API_KEY / SERPAPI_API_KEY / UPWORK_CLIENT_ID+SECRET
```

### Database

You need a PostgreSQL database with the `pgcrypto`, `pg_trgm`, `vector`, and
`citext` extensions available (the schema/migration creates them with
`CREATE EXTENSION IF NOT EXISTS`, but the extensions themselves must be
installed on the Postgres server/image, e.g. use the `pgvector/pgvector`
Docker image or install `postgresql-contrib` + `pgvector`).

Apply the schema with **either** of these (they are equivalent — the Alembic
migration replays `db/schema.sql` statement-by-statement so it can never
drift from that file):

```bash
# Option A: Alembic (recommended, tracks migration history)
alembic upgrade head

# Option B: apply db/schema.sql directly
python -m app.db.init_db
```

### Run the API

```bash
uvicorn app.main:app --reload
```

- API base: `http://localhost:8000/api/v1`
- Health check: `http://localhost:8000/health`
- Interactive docs: `http://localhost:8000/docs`

### Run tests

```bash
pytest
```

Tests are fully offline (no live network calls, no live database) — they
exercise `match_engine.py` (skill overlap, experience-years extraction,
weighted scoring), `job_importer.py` (JSON-LD parsing against a sample
`JobPosting` HTML fixture, and heuristic fallback parsing against plain HTML
with no JSON-LD), and the three search integrations (`google_jobs.py`,
`himalayas.py`, `upwork.py` — normalization, salary/date parsing, OAuth URL
building, and cache expiry, all with `httpx` mocked; no live calls to
serpapi.com / himalayas.app / api.upwork.com are made by the suite).

## Live job search

`GET /jobs/search?provider=himalayas|google_jobs|upwork` and
`POST /jobs/search/import` are documented in `../docs/API_CONTRACT.md`.

- **Himalayas** needs no configuration.
- **Google Jobs** (SerpApi) needs `SERPAPI_API_KEY` — get one at
  [serpapi.com](https://serpapi.com). Without it, `provider=google_jobs`
  returns a clean `503`.
- **Upwork** needs a registered app at
  [upwork.com/developer/apps](https://www.upwork.com/developer/apps) —
  set `UPWORK_CLIENT_ID`/`UPWORK_CLIENT_SECRET`, and make sure the redirect
  URI you register there matches `UPWORK_REDIRECT_URI` exactly. Each user
  then connects their own account via `GET /integrations/upwork/authorize`
  (an OAuth2 authorization-code flow — tokens are stored per-user in the
  `oauth_connections` table and refreshed automatically). Without an app
  configured, `GET /integrations/upwork/authorize` returns `503` and the
  frontend hides the Upwork tab behind a setup notice instead.

The exact GraphQL field names in `upwork.py`'s `marketplaceJobPostings`
query follow Upwork's publicly documented schema at the time of writing;
Upwork's schema is only fully browsable via GraphQL introspection from an
approved developer account, so if it returns a "Cannot query field ..."
error, adjust `_SEARCH_QUERY`/`_build_filter()` in that file against your
account's live schema — nothing else in the OAuth/caching/persistence flow
is affected by that.

## Project layout

```
app/
  main.py                  FastAPI app, CORS, router wiring, /health
  core/config.py           pydantic-settings (env vars)
  core/security.py         password hashing (bcrypt) + JWT
  db/session.py            async SQLAlchemy engine/session
  db/init_db.py            convenience: apply db/schema.sql directly
  models/                  SQLAlchemy models mirroring db/schema.sql
  schemas/                 Pydantic request/response models (API_CONTRACT.md)
  api/deps.py              get_current_user (JWT bearer auth)
  api/v1/routers/          auth, profile, jobs, match, applications, resumes, cover_letters, integrations
  services/
    skills_taxonomy.py     built-in skills taxonomy + synonym normalization
    job_importer.py        URL -> structured Job (JSON-LD first, heuristic fallback)
    match_engine.py         hybrid weighted match score (technical/experience/semantic)
    resume_adapter.py       ATS-safe tailored resume (AI when configured, rule-based fallback)
    cover_letter_generator.py  personalized cover letter (AI when configured, template fallback)
    google_jobs.py          Google Jobs search via SerpApi (server-side API key)
    himalayas.py             Himalayas remote-jobs search (no key needed)
    upwork.py                 Upwork OAuth2 + GraphQL job search (per-user token)
alembic/                   migrations (0001 mirrors db/schema.sql)
tests/                     pytest suite (match_engine, job_importer, google_jobs, himalayas, upwork)
```

## Auth

All routes except `POST /auth/register`, `POST /auth/login`, and `/health`
require `Authorization: Bearer <jwt>`. Every resource (career profile, jobs
you imported are shared/global, but matches/applications/resumes/cover
letters) is scoped so a user only ever sees their own data.

## Notable design choices / deviations

- **Jobs are shared, per-user data (matches, applications, resumes, cover
  letters) is scoped.** `jobs` has no `user_id` in the schema — `imported_by`
  just records who first imported it — so any authenticated user can view any
  job, but `job_matches`, `applications`, `resume_versions`, and
  `cover_letters` are always filtered by the current user.
- **`GET /jobs` `status` filter** matches the current user's `applications.status`
  for that job (jobs themselves have no status column).
- **`GET /matches`** returns the same `{items, total}` envelope as `GET /jobs`
  for consistency, with each `Job` item's `match` field populated — this
  satisfies "queue of Job + match" from the contract without introducing a
  second response shape.
- **Semantic score** is a dependency-free TF-IDF/cosine-similarity fallback
  over profile text (headline + summary + experience bullets) vs. job text
  (title + description) — no external API or ML library required. If
  `ANTHROPIC_API_KEY` is set, resume adaptation and cover-letter generation
  additionally use Claude (`claude-sonnet-5`) for higher-quality language
  adaptation; the match engine's semantic score always uses the offline
  method by design (per the task spec) so matching works with zero external
  dependencies.
- **Resume export** (`GET /resume-versions/{id}/export`) returns an ATS-safe
  plain-text rendering (`text/plain`, `Content-Disposition: attachment`)
  rather than a PDF, to avoid pulling in a PDF-rendering dependency for an
  MVP; the plain-text format is itself the most ATS-safe option.
