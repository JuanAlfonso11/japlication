-- JobFlow AI - PostgreSQL schema
-- Requires: pgcrypto (uuid generation), pg_trgm (fuzzy text search), vector (pgvector, optional semantic search)

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;

-- =========================================================
-- users
-- =========================================================
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               CITEXT UNIQUE NOT NULL,
    hashed_password     TEXT NOT NULL,
    full_name           TEXT NOT NULL,
    email_verified      BOOLEAN NOT NULL DEFAULT false,
    email_verified_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================================================
-- device_tokens (FCM push-notification tokens, one row per installed app)
-- =========================================================
CREATE TABLE device_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       TEXT UNIQUE NOT NULL,
    platform    TEXT NOT NULL DEFAULT 'android',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_device_tokens_user ON device_tokens (user_id);

-- =========================================================
-- refresh_tokens (long-lived "stay logged in" credential; the access JWT
-- is short-lived and gets renewed via one of these). Stores a hash, not
-- the raw token, and is revocable (logout, rotation on each use) -- unlike
-- the JWT it hands out, which nothing can invalidate before it expires.
-- =========================================================
CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens (user_id);
CREATE INDEX idx_refresh_tokens_hash ON refresh_tokens (token_hash);

-- =========================================================
-- career_profiles  (the "CV Maestro" - factual, user-owned truth)
-- =========================================================
CREATE TABLE career_profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    headline        TEXT,
    summary         TEXT,
    contact_info    JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {phone, city, country, linkedin, github, portfolio}
    skills          JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{name, category, level, years_experience}]
    experience      JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{company, title, start_date, end_date, location, bullets:[...], skills_used:[...]}]
    education       JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{institution, degree, field, start_date, end_date}]
    certifications  JSONB NOT NULL DEFAULT '[]'::jsonb,
    languages       JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{name, level}]
    -- Reusable answers to the screening questions every application form
    -- asks again (work authorization, notice period, salary expectation,
    -- ...). Written once here, surfaced per-job in the application kit with
    -- a copy button, so the repetitive part of applying stops being retyped.
    -- [{question, answer}]
    screening_answers JSONB NOT NULL DEFAULT '[]'::jsonb,
    embedding       VECTOR(1536),                          -- optional semantic embedding of the full profile
    search_vector   TSVECTOR GENERATED ALWAYS AS (
                        to_tsvector('spanish', coalesce(headline,'') || ' ' || coalesce(summary,''))
                    ) STORED,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_career_profiles_skills_gin ON career_profiles USING gin (skills jsonb_path_ops);
CREATE INDEX idx_career_profiles_search ON career_profiles USING gin (search_vector);

-- =========================================================
-- jobs  (normalized job postings, imported from a URL or search)
-- =========================================================
-- Every value here is a source that needs zero credentials to query — see
-- docs/PUBLIC_APIS_RESEARCH.md for what was investigated (including why
-- Google Jobs/Upwork were removed, and why LinkedIn/Indeed aren't — and
-- likely can't be — options for a personal project at all).
CREATE TYPE job_source AS ENUM (
    'url_import', 'himalayas', 'arbeitnow', 'remotive', 'jobicy', 'remotejobs_org', 'themuse',
    'weworkremotely', 'hackernews', 'adzuna', 'usajobs', 'getonbrd', 'serpapi',
    'workingnomads', 'remoteok', 'manual'
);

CREATE TABLE jobs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    imported_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    source            job_source NOT NULL DEFAULT 'url_import',
    source_url        TEXT UNIQUE,
    title             TEXT NOT NULL,
    company           TEXT NOT NULL,
    location          TEXT,
    remote_type       TEXT,               -- remote | hybrid | onsite | unknown
    employment_type   TEXT,               -- full_time | part_time | contract | internship
    seniority         TEXT,
    description       TEXT NOT NULL,
    requirements      JSONB NOT NULL DEFAULT '[]'::jsonb,  -- ["3+ years Python", ...]
    responsibilities  JSONB NOT NULL DEFAULT '[]'::jsonb,
    skills_required   JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{name, importance: required|nice_to_have}]
    salary_min        NUMERIC,
    salary_max        NUMERIC,
    salary_currency    TEXT,
    posted_at         TIMESTAMPTZ,
    raw_html          TEXT,
    requires_cover_letter BOOLEAN NOT NULL DEFAULT FALSE,
    embedding         VECTOR(1536),
    search_vector     TSVECTOR GENERATED ALWAYS AS (
                          to_tsvector('spanish',
                              coalesce(title,'') || ' ' || coalesce(company,'') || ' ' || coalesce(description,''))
                      ) STORED,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_jobs_search ON jobs USING gin (search_vector);
CREATE INDEX idx_jobs_skills_gin ON jobs USING gin (skills_required jsonb_path_ops);
CREATE INDEX idx_jobs_company_trgm ON jobs USING gin (company gin_trgm_ops);
CREATE INDEX idx_jobs_imported_by ON jobs (imported_by);

-- =========================================================
-- job_matches (cached hybrid match-engine output per user/job pair)
-- =========================================================
CREATE TABLE job_matches (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id              UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    overall_score       NUMERIC(5,2) NOT NULL,      -- 0-100
    -- NULL on a sub-score means unknown: the posting listed no skills, or
    -- stated no years requirement. Storing 100 for that (what this did until
    -- migration 0008) ranked postings nothing was known about above every
    -- job the engine could read. See services/match_engine.py.
    technical_score     NUMERIC(5,2),
    experience_score    NUMERIC(5,2),
    semantic_score      NUMERIC(5,2),
    matched_skills      JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_skills      JSONB NOT NULL DEFAULT '[]'::jsonb,
    concerns            JSONB NOT NULL DEFAULT '[]'::jsonb,   -- ["Requires 5+ years, profile has 3", ...]
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id)
);

CREATE INDEX idx_job_matches_user_score ON job_matches (user_id, overall_score DESC);

-- =========================================================
-- applications (swipe decisions + application lifecycle)
-- =========================================================
CREATE TYPE application_status AS ENUM (
    'queued', 'passed', 'saved', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn'
);
CREATE TYPE swipe_decision AS ENUM ('right', 'left');

CREATE TABLE applications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id              UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    status              application_status NOT NULL DEFAULT 'queued',
    decision            swipe_decision,
    match_score         NUMERIC(5,2),
    resume_version_id   UUID,   -- FK added below after resume_versions exists
    cover_letter_id     UUID,   -- FK added below after cover_letters exists
    notes               TEXT,
    applied_at          TIMESTAMPTZ,
    stale_notified_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id)
);

CREATE INDEX idx_applications_user_status ON applications (user_id, status);

-- =========================================================
-- resume_versions (ATS-safe, job-tailored resume snapshots)
-- =========================================================
CREATE TYPE generation_source AS ENUM ('manual', 'ai');

CREATE TABLE resume_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    career_profile_id   UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    job_id              UUID REFERENCES jobs(id) ON DELETE SET NULL,
    title               TEXT NOT NULL,
    content             JSONB NOT NULL,   -- rendered ATS-safe sections: {summary, skills[], experience[], education[]}
    change_log          JSONB NOT NULL DEFAULT '[]'::jsonb,  -- diffs vs. career_profile for transparency/audit
    generated_by        generation_source NOT NULL DEFAULT 'ai',
    -- Set the first time the user edits a generated version. Two jobs: it
    -- marks the text as carrying the user's own corrections rather than only
    -- the generator's wording, and that makes it the better starting point
    -- when a later, similar posting looks for a resume to reuse (see
    -- _find_reusable_resume). Their edits therefore carry forward instead of
    -- being re-made every time.
    edited_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================================================
-- error_logs  (todo lo que falla, en un solo lugar consultable)
-- =========================================================
-- Antes de esto, un error del backend vivia en el stdout de Docker (efimero,
-- y hay que saber ir a buscarlo) y un error del frontend en el telefono no
-- existia en ningun lado. Esta tabla es el sitio unico donde mirar cuando
-- algo falla.
--
-- Lo que NO se guarda, a proposito: el cuerpo de la peticion. Un POST a
-- /auth/login lo primero que lleva es una contrasena, y un log que la captura
-- convierte un problema de diagnostico en una filtracion de credenciales.
-- Se guarda de donde vino el error y que fallo, nunca con que datos.
CREATE TABLE error_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Correlaciona una respuesta de error que vio el usuario con su fila
    -- aqui: el API devuelve este id y el usuario solo tiene que leerlo.
    request_id    TEXT NOT NULL,
    -- 'backend' | 'frontend' — de que lado ocurrio.
    source        TEXT NOT NULL,
    -- 'error' | 'warning'
    level         TEXT NOT NULL DEFAULT 'error',
    -- Nombre de la excepcion o del error JS.
    kind          TEXT,
    message       TEXT NOT NULL,
    -- Traceback (backend) o stack (frontend), recortado.
    stack         TEXT,
    -- Contexto de la peticion: metodo + ruta (sin query, que puede llevar
    -- datos), y el codigo de estado devuelto.
    method        TEXT,
    path          TEXT,
    status_code   INTEGER,
    -- Quien lo sufrio, si habia sesion. ON DELETE SET NULL para que borrar
    -- un usuario no borre el historial de fallos.
    user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
    -- Solo para errores de frontend: que navegador/WebView y en que URL.
    user_agent    TEXT,
    url           TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- La consulta que se hace siempre: los ultimos primero.
CREATE INDEX idx_error_logs_created_at ON error_logs (created_at DESC);
CREATE INDEX idx_error_logs_request_id ON error_logs (request_id);

CREATE INDEX idx_resume_versions_user ON resume_versions (user_id);
CREATE INDEX idx_resume_versions_job ON resume_versions (job_id);

-- =========================================================
-- cover_letters
-- =========================================================
CREATE TABLE cover_letters (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id              UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_version_id   UUID REFERENCES resume_versions(id) ON DELETE SET NULL,
    content             TEXT NOT NULL,
    tone                TEXT NOT NULL DEFAULT 'professional',
    generated_by        generation_source NOT NULL DEFAULT 'ai',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_cover_letters_user ON cover_letters (user_id);
CREATE INDEX idx_cover_letters_job ON cover_letters (job_id);

-- =========================================================
-- system_heartbeats — one row per scheduled background job
-- (job_sweep / stale_check / backup / watchdog), POSTed by each
-- scripts/*.ps1 right after it runs, so Profile's "Estado del sistema"
-- panel can show whether the machinery behind the app is alive.
-- =========================================================
CREATE TABLE system_heartbeats (
    job_name        TEXT PRIMARY KEY,
    last_run_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_status     TEXT NOT NULL DEFAULT 'ok',
    detail          TEXT
);

-- =========================================================
-- api_call_budgets — one row per (provider, calendar day), tracks how many
-- times a monthly-quota external API (Adzuna, SerpApi) has been called
-- today. app.services.api_budget enforces a daily cap from this so an
-- unattended background sweep can never silently blow through a monthly
-- quota (see docs/PUBLIC_APIS_RESEARCH.md for each provider's real limit).
-- =========================================================
CREATE TABLE api_call_budgets (
    provider        TEXT NOT NULL,
    call_date       DATE NOT NULL,
    call_count      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, call_date)
);

-- Back-fill FKs on applications now that the referenced tables exist
ALTER TABLE applications
    ADD CONSTRAINT fk_applications_resume_version
        FOREIGN KEY (resume_version_id) REFERENCES resume_versions(id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_applications_cover_letter
        FOREIGN KEY (cover_letter_id) REFERENCES cover_letters(id) ON DELETE SET NULL;

-- =========================================================
-- updated_at triggers
-- =========================================================
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_career_profiles_updated_at BEFORE UPDATE ON career_profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_jobs_updated_at BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_applications_updated_at BEFORE UPDATE ON applications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_device_tokens_updated_at BEFORE UPDATE ON device_tokens
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
