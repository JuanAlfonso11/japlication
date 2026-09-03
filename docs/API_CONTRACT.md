# JobFlow AI — API Contract (v1)

Base URL: `http://localhost:8000/api/v1`
Auth: `Authorization: Bearer <jwt>` (except `/auth/register`, `/auth/login`)
All bodies/responses are JSON. IDs are UUID strings. Timestamps are ISO-8601.

## Auth
- `POST /auth/register` `{email, password, full_name}` -> `{access_token, token_type, user}`
- `POST /auth/login` `{email, password}` -> `{access_token, token_type, user}`
- `GET /auth/me` -> `User`

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

## Live job search (Google Jobs / Himalayas / Upwork)
Search results are **not persisted** — pick one and call the import endpoint to add it to `jobs`.

- `GET /jobs/search?provider=himalayas|google_jobs|upwork&q=&location=&country=&worldwide=&seniority=&employment_type=&sort=&page=&next_page_token=`
  -> `{provider, results: ExternalJobResult[], next_page_token?, page?, has_more}`
  - `provider` defaults to `himalayas` (free, no key). `google_jobs` requires the backend's `SERPAPI_API_KEY`
    (else `503`). `upwork` requires the user to have connected their account (else `409`) — see below.
  - `ExternalJobResult`: same shape as `Job` (minus id/timestamps) plus `external_id` and `source`.
    ```json
    {
      "external_id": "hj-001", "source": "himalayas",
      "source_url": "https://...", "title": "Senior React Engineer", "company": "Northbeam",
      "location": "United States, Canada", "remote_type": "remote", "employment_type": "full_time",
      "description": "...", "requirements": ["..."], "skills_required": [{"name": "React", "importance": "required"}],
      "salary_min": 90000, "salary_max": 120000, "salary_currency": "USD", "posted_at": "2023-11-14T22:13:20Z"
    }
    ```
- `POST /jobs/search/import` `{source, external_id}` -> `Job` (reads the normalized result from that
  provider's short-lived search cache — re-run the search if it expired, `404`)

## Integrations (Upwork OAuth2)
Upwork needs per-user authorization (unlike Google Jobs' single server-side API key), so it's a separate
connect flow:
- `GET /integrations/upwork/status` -> `{connected: bool, configured: bool}`
- `GET /integrations/upwork/authorize` -> `{authorization_url}` (frontend does `window.location.href = ...`)
- `GET /integrations/upwork/callback?code=&state=` -> not called by the frontend directly; Upwork redirects
  the browser here, which redirects again to `{FRONTEND_ORIGIN}/discover?upwork=connected|error`
- `DELETE /integrations/upwork` -> disconnects (204)

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
