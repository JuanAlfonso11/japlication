# JobFlow AI — Backend

FastAPI backend for JobFlow AI, a personal job-search / application assistant.

## Stack

- Python 3.11, FastAPI, SQLAlchemy 2.0 (async, asyncpg), Pydantic v2, Alembic
- PostgreSQL (schema defined in `../db/schema.sql`, the source of truth)
- Optional: Anthropic API (`claude-sonnet-5`) for AI-powered resume tailoring,
  cover letters, CV-PDF parsing, and job parsing upgrades — every one of
  these features has a fully-functional deterministic/offline fallback when
  no API key is set.
- Optional: live job search — 6 providers, none of which need any key. See
  "Live job search" below.
- Email verification on signup via SMTP (`smtplib`) — falls back to logging
  the verification link when `SMTP_HOST` isn't set, so local dev needs no
  mail account. See "Auth & email verification" below.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set DATABASE_URL, JWT_SECRET, FRONTEND_ORIGIN, and (optionally)
# ANTHROPIC_API_KEY / SMTP_* (see "Auth & email verification" below)
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
with no JSON-LD), `experience_level.py` (keyword inference + native-value
mapping for Himalayas/The Muse/Jobicy), `cv_upload.py` (PDF text extraction
errors, heuristic contact/skills parsing, AI-vs-heuristic selection),
`email.py` (SMTP-configured vs. logged-link fallback), and all six search
integrations (`himalayas.py`, `arbeitnow.py`, `remotive.py`, `jobicy.py`,
`remotejobs_org.py`, `themuse.py` — normalization, salary/date parsing, and
cache expiry, all with `httpx` mocked; no live calls to any of those
providers are made by the suite).

## Live job search

`GET /jobs/search/aggregate` (all 6 providers at once — what Discover uses),
`GET /jobs/search?provider=` (single provider), and `POST /jobs/search/import` are documented in
`../docs/API_CONTRACT.md`. The research behind each provider (endpoint, params, response shape, rate
limits) — plus why Google Jobs and Upwork were removed and why LinkedIn/Indeed were never options for a
personal project — is in `../docs/PUBLIC_APIS_RESEARCH.md`.

**Himalayas, Arbeitnow, Remotive, Jobicy, RemoteJobs.org, The Muse** need no configuration — zero API
keys, zero OAuth, zero signup. `app/services/experience_level.py` normalizes each one's notion of
seniority (native where the provider has it, inferred from title/description otherwise) into one shared
`internship|entry|mid|senior|lead` taxonomy so the level filter works uniformly across all six.

## Auth & email verification

`POST /auth/register` sends a verification email in the background (never blocks or fails registration
over it) with a signed, 24h link to `GET /auth/verify-email?token=`. Configure `SMTP_HOST` (+
`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM_EMAIL`/`SMTP_USE_TLS`) to send real emails via any SMTP
provider (Gmail app password, Mailtrap for local testing, SendGrid/Postmark/SES SMTP relay, ...); without
it, `app/services/email.py` just logs the verification link instead, so registration/login/verification
can all be exercised locally with zero mail setup. Login is **not** blocked on verification — the frontend
shows a persistent "confirm your email" banner with a resend button instead, so a flaky mail provider
never locks someone out of their own account.

## PDF CV upload

`POST /profile/import-cv` (`app/services/cv_upload.py`) extracts text from an uploaded PDF (`pypdf`) and
returns a draft `CareerProfileUpsert` — never persisted by itself; the frontend pre-fills the profile
editor and the user still has to review it and hit Save. Claude does the actual extraction when
`ANTHROPIC_API_KEY` is set (`generated_by: "ai"`); without it, a regex/skills-taxonomy heuristic reliably
pulls contact info and a flat skills list but deliberately leaves `experience`/`education` empty rather
than guess at a resume's layout (`generated_by: "heuristic"`, with `warnings` explaining why).

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
  api/v1/routers/          auth, profile, jobs, match, applications, resumes, cover_letters
  services/
    skills_taxonomy.py     built-in skills taxonomy + synonym normalization
    job_importer.py        URL -> structured Job (JSON-LD first, heuristic fallback)
    match_engine.py         hybrid weighted match score (technical/experience/semantic)
    resume_adapter.py       ATS-safe tailored resume (AI when configured, rule-based fallback)
    cover_letter_generator.py  personalized cover letter (AI when configured, template fallback)
    cv_evaluator.py          CV quality check, independent of any job (AI summary when configured)
    cv_upload.py               PDF résumé -> draft CareerProfile (AI when configured, heuristic fallback)
    email.py                    SMTP sender for account verification (logs the link when unconfigured)
    experience_level.py     shared internship/entry/mid/senior/lead taxonomy
    himalayas.py             search: Himalayas remote-jobs
    arbeitnow.py             search: Arbeitnow job board
    remotive.py               search: Remotive remote-jobs
    jobicy.py                   search: Jobicy remote-jobs
    remotejobs_org.py         search: RemoteJobs.org
    themuse.py                 search: The Muse (api_key optional)
alembic/                   migrations (0001 mirrors db/schema.sql)
tests/                     pytest suite (match_engine, job_importer, cv_evaluator, cv_upload, email,
                           experience_level, himalayas, arbeitnow, remotive, jobicy, remotejobs_org, themuse)
```

## CV Evaluator

`GET /profile/evaluation` scores the user's career profile on its own merits — completeness, quantified/
strong-language impact of experience bullets, skills coverage, and ATS-safety — separate from the Match
Engine, which scores a profile *against one job*. Fully rule-based and offline by default
(`app/services/cv_evaluator.py`); when `ANTHROPIC_API_KEY` is set, the one-paragraph `summary` field is
written by Claude instead of a templated fallback sentence, using the already-computed scores/issues as
context (not the raw profile) so it can't contradict them.

## Auth

All routes except `POST /auth/register`, `POST /auth/login`, `GET /auth/verify-email`, and `/health`
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
