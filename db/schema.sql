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
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           CITEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
CREATE TYPE job_source AS ENUM ('url_import', 'google_jobs', 'linkedin', 'indeed', 'manual');

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
    technical_score     NUMERIC(5,2) NOT NULL,
    experience_score    NUMERIC(5,2) NOT NULL,
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
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
