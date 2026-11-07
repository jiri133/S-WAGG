# Scheme Pydantic, mock-uri FastAPI și schelet React cu tipuri generate

Type: task
Status: open
Owner: Tu + Alina
Țintă: H2
Blocked by: 03, 04

## Question

**Primul pas (din tichetul 01):** `cd backend && uv python pin 3.14` și `requires-python = ">=3.11,<3.15"` în `pyproject.toml`.

Spec: §9 (scheme și endpoint-uri) și §10–11.

- `backend/app/schemas/`: toate modelele din §9, împărțite pe fișiere (`park.py`, `mission.py`, `finding.py`, `actions.py`, `stream.py`).
- `backend/app/api/routes/`: un router per grup din tabelul §9, care întoarce **mock-uri cu forma finală**, plus SSE mock.
- `frontend`: `npm i zustand recharts` și `npm i -D openapi-typescript`, scriptul `gen:types` → `src/api/types.gen.ts` din `http://localhost:8000/api/openapi.json`, `missionStore.ts` gol, `api.ts` tipizat.

**Gata când:** React afișează parcul din `GET /api/park` (mock), iar `uv run pytest -q` și `npm run build` trec.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Instalează Node 22+ pe laptopul tău](03-node-tu.md)
- [Acces GitHub și setup pe laptopul Alinei](04-alina-setup.md)
