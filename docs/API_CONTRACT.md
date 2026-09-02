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
