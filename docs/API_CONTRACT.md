# JobFlow AI — API Contract (v1)

Base URL: `http://localhost:8000/api/v1`
Auth: `Authorization: Bearer <jwt>` (except `/auth/register`, `/auth/login`)
All bodies/responses are JSON. IDs are UUID strings. Timestamps are ISO-8601.

## Auth
- `POST /auth/register` `{email, password, full_name}` -> `{access_token, refresh_token, token_type, user}` (201).
  Also sends a verification email in the background (see below) — registration succeeds and returns a
  usable token even if that email fails to send; the user can always request another one.
- `POST /auth/login` `{email, password}` -> `{access_token, refresh_token, token_type, user}`
- `POST /auth/refresh` `{refresh_token}` -> `{access_token, refresh_token, token_type}` (no auth header —
  identity comes from the refresh token itself). `access_token` is short-lived
  (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 30 min); call this to get a new one before/when it expires.
  Rotates on every call — the `refresh_token` used is revoked and a new one is returned, so always store
  the new one and discard the old. 401 if the refresh token is invalid, expired, or already revoked
  (session is over — the user has to log in again).
- `POST /auth/logout` `{refresh_token}` -> 204. Revokes that refresh token server-side. Best-effort/
  idempotent — always 204 even if the token was already gone.
- `GET /auth/me` -> `User` (includes `email_verified`, `email_verified_at`)
- `POST /auth/resend-verification` (auth required) -> `{sent: bool, detail: string}` — no-ops with
  `sent: false` if already verified.
- `GET /auth/verify-email?token=` -> not called by the frontend directly; this is the link in the
  verification email. No Authorization header (identity comes from the signed `token`) — always ends in a
  redirect to `{FRONTEND_ORIGIN}/verify-email?status=success|invalid`.

**Email delivery**: `app/services/email.py` sends via SMTP (`SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/
`SMTP_PASSWORD`/`SMTP_FROM_EMAIL`/`SMTP_USE_TLS`). Without `SMTP_HOST` configured, nothing is actually
sent — the backend logs the verification link instead, so local dev needs no mail account at all.

## Career Profile (CV Maestro)
- `GET /profile` -> `CareerProfile` (404 if not created yet)
- `PUT /profile` upsert full profile -> `CareerProfile`
  ```json
  {
    "headline": "Senior Backend Engineer",
    "summary": "...",
    "contact_info": {"phone": "", "city": "", "country": "", "linkedin": "", "github": "", "portfolio": ""},
    "skills": [{"name": "C#", "category": "language", "level": "advanced", "years_experience": 4}],
    "experience": [{"company": "", "title": "", "start_date": "2021-01", "end_date": null, "location": "", "bullets": ["..."], "skills_used": ["C#", "SQL"]}],
    "education": [{"institution": "", "degree": "", "field": "", "start_date": "", "end_date": ""}],
    "certifications": [{"name": "", "issuer": "", "date": ""}],
    "languages": [{"name": "English", "level": "C1"}]
  }
  ```
- `POST /profile/import-cv` — `multipart/form-data`, field `file` (a PDF, max `MAX_CV_UPLOAD_MB`, default
  8MB) -> `CVUploadResult`:
  ```json
  {"profile": { /* same shape as CareerProfileUpsert above, only fields found in the PDF are filled */ },
   "generated_by": "ai" | "heuristic",
   "warnings": ["..."]}
  ```
  **Nothing is persisted by this call** — the frontend pre-fills the profile editor with the draft and the
  user still has to review it and call `PUT /profile` themselves. `generated_by: "ai"` (Claude parses the
  extracted PDF text) when `ANTHROPIC_API_KEY` is set; otherwise `"heuristic"` (regex/skills-taxonomy based —
  reliably extracts contact info and a flat skills list, but deliberately leaves `experience`/`education`
  empty rather than guess at structure it can't parse safely — `warnings` explains this to the user).

## Jobs
- `POST /jobs/import` `{url}` -> `Job` (fetches URL, parses to structured JSON, persists; idempotent on `source_url`)
- `POST /jobs` manual creation (same body shape as parsed Job, for pasting a description directly) -> `Job`
- `GET /jobs?query=&status=&min_score=&limit=&offset=` -> `{items: Job[], total}`
- `GET /jobs/{id}` -> `Job` (includes cached `match` if present for the current user)
- `DELETE /jobs/{id}`

`Job.skills_required` is `[{name, importance: "required"|"nice_to_have"}]`.

## CV Evaluator (profile quality, independent of any job)
- `GET /profile/evaluation` -> `CVEvaluation` (404 if no profile yet). Rule-based, always available offline;
  scores the CV Maestro on its own merits — not against a specific job (that's the Match Engine below).
  ```json
  {
    "overall_score": 78.5,
    "band": "Sólido",
    "categories": {
      "completeness": {"score": 90, "issues": [{"severity": "info", "category": "completeness", "message": "..."}]},
      "impact": {"score": 65, "issues": [...]},
      "skills_breadth": {"score": 85, "issues": [...]},
      "ats_safety": {"score": 100, "issues": []}
    },
    "top_issues": [{"severity": "warning", "category": "impact", "message": "Solo 2 de 8 logros incluyen números o métricas..."}],
    "strengths": ["Buena parte de tus logros incluyen métricas concretas..."],
    "summary": "One or two sentence coach-style summary.",
    "summary_generated_by": "manual"
  }
  ```
  `summary` is AI-written (`summary_generated_by: "ai"`) when `ANTHROPIC_API_KEY` is configured, else a
  deterministic fallback sentence built from the top issue.

## Live job search
Search results are **not persisted** — pick one and call the import endpoint to add it to `jobs`.

Six providers, all requiring **zero credentials** (no API key, no OAuth, no signup) — see
`docs/PUBLIC_APIS_RESEARCH.md` for the full research behind each one, including why Google Jobs and Upwork
(both credential-gated) were deliberately removed, and why LinkedIn/Indeed aren't — and likely can't be —
options for a personal project at all: `himalayas`, `arbeitnow`, `remotive`, `jobicy`, `remotejobs_org`,
`themuse`.

- `GET /jobs/search/aggregate?q=&location=&remote_type=remote&experience_level=&category=`
  -> `{results: ExternalJobResult[], sources: [{provider, count, error?}]}`
  — fans out to **all six providers in parallel** and merges the results, newest first. This is what
  Discover's search calls. A provider that errors doesn't drop the others' results; its failure shows up in
  `sources` instead. `location` and `remote_type` are independent filters: `location` is purely geographic
  (e.g. `"Mexico"`, `"Europe"` — unset means any location) while `remote_type` is one of
  `remote|hybrid|onsite` and defaults to `remote` when omitted, preserving the historical default of
  showing remote-friendly postings first. `experience_level` is one of
  `internship|entry|mid|senior|lead` (see below).
- `GET /jobs/search?provider=himalayas|arbeitnow|remotive|jobicy|remotejobs_org|themuse&q=&location=&experience_level=&remote_type=&category=&country=&worldwide=&seniority=&employment_type=&sort=&page=`
  -> `{provider, results: ExternalJobResult[], page?, has_more}` — single-provider search, for querying just
  one source directly instead of all six.
  - `provider` defaults to `himalayas`. `remote_type` (`remote|hybrid|onsite`) is optional here — unset means
    no filtering by work mode.
  - `ExternalJobResult`: same shape as `Job` (minus id/timestamps) plus `external_id` and `source`.
    `seniority` holds the normalized experience level (`internship|entry|mid|senior|lead`) whenever it could
    be determined — natively from the provider (Himalayas, The Muse, Jobicy) or inferred from the title/
    description text (Arbeitnow, Remotive, RemoteJobs.org) via `app/services/experience_level.py`.
    ```json
    {
      "external_id": "hj-001", "source": "himalayas",
      "source_url": "https://...", "title": "Senior React Engineer", "company": "Northbeam",
      "location": "United States, Canada", "remote_type": "remote", "employment_type": "full_time",
      "seniority": "senior",
      "description": "...", "requirements": ["..."], "skills_required": [{"name": "React", "importance": "required"}],
      "salary_min": 90000, "salary_max": 120000, "salary_currency": "USD", "posted_at": "2023-11-14T22:13:20Z"
    }
    ```
- `POST /jobs/search/import` `{source, external_id}` -> `Job` (reads the normalized result from that
  provider's short-lived search cache — re-run the search if it expired, `404`)
- `POST /jobs/search/auto-import` -> `{imported: int, query?: string, sources: [{provider, count, error?}]}`
  — searches all six providers using the saved career profile (headline, most recent role, or top
  skills, whichever is available first) and imports the newest matches into `jobs` with a computed
  match score in one call, so they show up in `GET /matches` immediately. This is what the frontend
  calls right after a CV-derived profile is saved (`POST /profile/import-cv` followed by
  `PUT /profile`), so Home's swipe queue has something to show without a manual Discover search.
  Only genuinely new postings (by `source_url`) are imported/counted. `400` if no career profile
  exists yet, or if it has no headline, experience, or skills to search by.

## Match Engine
- `GET /jobs/{id}/match` -> computes (or returns fresh cached) `MatchResult`, recompute with `?refresh=true`
  ```json
  {
    "overall_score": 78.5,
    "technical_score": 82.0,
    "experience_score": 70.0,
    "semantic_score": 75.0,
    "matched_skills": ["C#", "SQL", "REST APIs"],
    "missing_skills": ["Kubernetes"],
    "concerns": ["Requiere 5+ años de liderazgo; el perfil registra 2."]
  }
  ```
- `GET /matches?min_score=&limit=&offset=` -> queue of `Job` + `match` for the swipe feed, sorted by `overall_score` desc, excluding jobs already decided.

## Applications (swipe + pipeline)
- `POST /jobs/{id}/decision` `{decision: "right"|"left"}` -> `Application` (right => status `saved`, left => status `passed`)
- `GET /applications?status=` -> `Application[]` (joined with `Job` summary)
- `GET /applications/{id}` -> `Application`
- `PATCH /applications/{id}` `{status?, notes?, applied_at?}` -> `Application`

## Resume adaptation
- `POST /jobs/{id}/resume` optional `{tone?}` -> generates ATS-safe `resume_versions` tailored to the job from the career profile -> `ResumeVersion`
- `GET /resume-versions/{id}` -> `ResumeVersion`
- `GET /resume-versions/{id}/export` -> ATS-safe plain text/PDF

## Cover letters
- `POST /jobs/{id}/cover-letter` optional `{tone?, resume_version_id?}` -> `CoverLetter`
- `GET /cover-letters/{id}` -> `CoverLetter`

## Error shape
```json
{"detail": "human readable message", "code": "job_not_found"}
```
