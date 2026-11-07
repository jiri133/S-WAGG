# Hackathon App

> One-line pitch goes here.

**Stack:** FastAPI + SQLModel (Python) · React + Vite + TypeScript + Tailwind v4

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), Node 22+ (or just Docker).

```bash
make setup   # install backend/frontend deps; create backend/.env, frontend/.env and RL/.env
make dev     # backend :8000 + frontend :5173
```

The RL package is installed separately; see `RL/README.md`.

- App: http://localhost:5173
- API docs (Swagger): http://localhost:8000/api/docs

With Docker instead: `make up`.

On Windows (PowerShell, no `make` needed):

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\dev.ps1
```

## Secrets

API keys and connection strings live in `.env` files: `backend/.env` and `RL/.env`. They are
gitignored; only the `.env.example` templates are tracked. `make setup` / `setup.ps1` copies
each template to `.env` if it does not exist. Fill in the keys you have locally and never
commit them.

Do not put secrets in `frontend/.env`: `VITE_*` values are bundled into the browser client.
`RL/scripts/check_env.py` reports which RL keys are set without printing their values.

## Structure

```
backend/
  app/
    main.py          FastAPI app, CORS, router mount (/api)
    api/router.py    register routers here
    api/routes/      one file per resource (health.py as example)
    api/deps.py      shared dependencies (SessionDep)
    core/config.py   settings from env vars / backend/.env
    core/db.py       engine + session (SQLite by default)
    models/          DB tables (SQLModel table=True)
    schemas/         request/response models
    services/        business logic, external APIs, AI calls
  tests/
frontend/
  src/
    api/client.ts    fetch wrapper -> /api (proxied to :8000 in dev)
    hooks/useApi.ts  data fetching hook
    components/      Layout + shared UI
    pages/           one file per route, register in App.tsx
    types/           TS types mirroring backend schemas
```

## Adding a feature (checklist)

1. Model in `backend/app/models/`, import it in `models/__init__.py`
2. Route in `backend/app/api/routes/x.py`, include it in `api/router.py`
3. Type in `frontend/src/types/`, page in `frontend/src/pages/`, route in `App.tsx`

## Team

| Name | Role |
| ---- | ---- |
|      |      |
