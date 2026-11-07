# Scheme Pydantic, mock-uri FastAPI și schelet React cu tipuri generate

Type: task
Status: resolved
Owner: Tu + Alina
Țintă: H2
Blocked by: 03

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

## Comments

- 2026-11-07 · Tu: deblocat de setup-ul Alinei. Pornește Tu cu un agent, Alina verifică schemele când ajunge.

## Answer

Gata: `uv run pytest -q` (32 teste) și `npm run build` trec. Cu ambele servere pornite, pagina `/` din React afișează cele 480 de module din `GET /api/park` (grilă simplă, verificată în browser, fără erori în consolă).

**Fișiere**

- `backend/.python-version` (3.14) și `requires-python = ">=3.11,<3.15"` în `backend/pyproject.toml`.
- `backend/app/schemas/`: `park.py` (FaultClass, Urgency, ModuleStatus, Module), `mission.py` (MissionSettings, Mission, FrameMeta), `finding.py` (Prediction, SimilarCase, Evidence, Finding, ReviewIn), `actions.py` (WorkOrder, PlanTask, PlanDay, Plan, Alert, AgentEvent), `stream.py` (StreamEvent). Câmpurile sunt exact cele din §9. Se importă din `app.schemas`.
- `backend/app/api/routes/`: `park.py`, `missions.py`, `findings.py`, `actions.py`, `mock.py`, `eval.py`, montate în `api/router.py` sub `/api`.
- `backend/app/services/mock_data.py`: parcul fix de 480 de module și datele mock (5 finding-uri, cadre, ordine, plan pe 3 zile cu o zi de ploaie, alertă, jurnal). Fiecare tichet ulterior înlocuiește câte o funcție de aici cu serviciul real.
- `backend/tests/test_contracts.py`: fiecare endpoint JSON validat pe modelul lui, plus PNG, CSV, HTML, SSE (toate cele 8 tipuri) și layout-ul parcului.
- `frontend/src/api/types.gen.ts` (generat, 46 KB, exceptat de regula de 30 KB), `frontend/src/api/api.ts` (`solarApi` cu fetch-uri tipizate și `urls` pentru img/CSV/iframe/EventSource), `frontend/src/store/missionStore.ts` (Zustand, doar `mission`), `frontend/src/pages/Main.tsx` (grila parcului pe `/`). Pagina de health din template s-a mutat pe `/status`.
- `.claude/launch.json`: pornește `backend` (:8000) și `frontend` (:5173) din panoul de preview.

**Endpoint-uri (toate sub `/api`)**

| Metodă | Endpoint | Răspuns |
|---|---|---|
| GET | `/park` | `Module[]` (480) |
| POST | `/missions` (body `MissionSettings`) · `/missions/demo/{scenario}` | `Mission` |
| GET | `/missions/{id}` | `Mission` |
| GET | `/missions/{id}/stream` | SSE, `data: <StreamEvent JSON>` |
| POST | `/missions/{id}/fly` · `/refly` · `/analyse` | `Mission` |
| GET | `/missions/{id}/frames` | `FrameMeta[]` |
| GET | `/frames/{id}/thumb.png` | PNG |
| GET | `/missions/{id}/findings` | `Finding[]` (după scor) |
| POST | `/findings/{id}/review` (body `ReviewIn`) | `Finding` |
| GET | `/findings/{id}/crop.png` · `/findings/{id}/gradcam.png` | PNG |
| GET | `/missions/{id}/work-orders?format=json\|csv` | `WorkOrder[]` sau CSV |
| GET | `/missions/{id}/labels.csv` | CSV |
| GET | `/missions/{id}/plan` | `Plan` |
| GET | `/missions/{id}/alerts` | `Alert[]` |
| POST | `/alerts/{id}/ack` | `Alert` |
| GET | `/missions/{id}/events` | `AgentEvent[]` |
| GET | `/missions/{id}/report` | HTML |
| GET | `/missions/{id}/score` | `dict[str, int]` (vezi mai jos) |
| POST | `/analyse` (multipart, câmpul `file`) | `Prediction` |
| GET/POST | `/mock/ticketing` | listă de payload-uri / confirmare |
| GET | `/eval` | conținutul `reports/eval.json`, 404 până îl scrie `evaluate.py` |

**Ce a lăsat spec-ul deschis (de confirmat cu Alina)**

1. §9 zice `backend/app/schemas.py`, §11 și tichetul zic pachetul `schemas/`. Am ales pachetul. Tipurile comune (FaultClass, Urgency, ModuleStatus) stau în `park.py`. Am adăugat doar două alias-uri de tip, fără câmpuri noi: `ReviewDecision` și `StreamEventType`.
2. **`/score` nu are schemă în §9.** Mock-ul întoarce `{true_positive, false_positive, missed, not_inspected}`. Trebuie decisă forma finală (probabil un model `Score`).
3. **`StreamEvent.data` e `dict` netipizat.** Payload-urile din mock: `waypoint` {x_m, y_m, table}, `frame_captured` = FrameMeta, `frame_checked` {frame_id, check_ok, problems}, `cloud` {irradiance_wm2}, `flight_done` {frames}, `findings_ready` {count}, `alert_raised` = Alert, `agent_event` = AgentEvent. SSE-ul trimite doar linii `data:` (fără `event:`), ca `EventSource.onmessage` să primească tot.
4. Răspunsul pentru `fly`/`refly`/`analyse` nu e dat. Întorc `Mission`, cu faza actualizată.
5. Formatul de intrare pentru `POST /analyse` nu e dat. Am ales upload multipart (`file`, PNG 24×40).
6. Coloanele din `labels.csv` nu sunt date. Am ales `module_id, predicted, review, note`. CSV-ul de ordine folosește câmpurile `WorkOrder`.
7. `/mock/ticketing` și `/eval` nu au schemă: `dict` liber.
8. Numele scenariilor demo (§12) nu sunt fixate: `{scenario}` e `str`.
9. `Module.pos` = poziția 1–12 în masă. `x_m`/`y_m` din mock: module portret 1,0 × 1,7 m, 1 m între mese, rânduri la 9 m, blocuri la 45 m. Geometria reală e a simulatorului (tichetul 16).
10. **`openapi-typescript` nu merge cu TypeScript 7** din template (TS 7 nu mai are API-ul JS de compilator, iar peer dependency-ul e `typescript@^5`). Așa că `npm run gen:types` îl rulează prin `npx` cu `typescript@5.9.3` și `openapi-typescript@7.13.0` fixate, deci nu e în `devDependencies`. Alternativa ar fi să coborâm proiectul pe TS 5.9.

**De știut**

- `gen:types` cere backend-ul pornit pe :8000. După orice schimbare de schemă: `npm run gen:types` și commit pe `types.gen.ts`.
- Pe laptopul meu, `fastapi dev` nu a prins singur modificările din `app/`. Dacă OpenAPI pare vechi, repornește backend-ul.
- `test_file_size.py` nu e făcut aici. E în tichetul 22.
- Mock-urile acceptă orice `mission_id` și întorc aceeași misiune.
