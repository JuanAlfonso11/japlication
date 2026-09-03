# JobFlow AI — Frontend

A Next.js (App Router) + TypeScript + Tailwind CSS frontend for JobFlow AI, a
personal job-search / application assistant. It talks to the JobFlow AI
FastAPI backend described in `../docs/API_CONTRACT.md`.

## Screens

- `/login`, `/register` — auth
- `/` — **home**: the Tinder-style match queue (drag, buttons, or arrow
  keys), recommended straight from the CV Maestro's match scores, plus a
  compact stats strip. This is the landing screen after login.
- `/discover` — live search across Himalayas / Google Jobs / Upwork; pick
  results to add to the home queue (does not persist anything by itself)
- `/jobs/import` — add one specific job you already found elsewhere, by URL
  or pasted text
- `/profile` — "CV Maestro" career profile editor
- `/jobs/[id]` — job detail, match breakdown, resume + cover letter generation
- `/applications` — pipeline dashboard with status filters and inline editing

## Getting started

```bash
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL if not using the default
npm run dev
```

The app runs at http://localhost:3000 and expects the backend at
`NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000/api/v1`).

## Scripts

- `npm run dev` — start the dev server
- `npm run build` — production build
- `npm run start` — run the production build
- `npm run lint` — run ESLint

## Environment variables

See `.env.example`:

- `NEXT_PUBLIC_API_URL` — base URL of the backend API, including the
  `/api/v1` prefix.

## Auth

The JWT returned by `/auth/login` and `/auth/register` is stored in
`localStorage` and attached to every API request as a `Bearer` token
(acceptable for this personal-use MVP — see `lib/api.ts` and
`context/AuthContext.tsx`). All routes other than `/login` and `/register`
are wrapped in a `RouteGuard` that redirects to `/login` when there is no
valid session.

## PWA

`public/manifest.json` plus icons in `public/icons/` make the app
installable on mobile and desktop. The layout sets `theme-color` and a
mobile-first viewport. No service worker is registered (kept out of scope
for this MVP) — pages are always fetched fresh.

## Docker

```bash
docker build -t jobflow-frontend --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 .
docker run -p 3000:3000 jobflow-frontend
```
