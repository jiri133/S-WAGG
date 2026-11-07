# Starea misiunii: SQLite, SSE, endpoint-urile de misiune

Type: task
Status: resolved
Owner: Tu
Țintă: H8
Blocked by: 05

## Question

Spec: §2, §9 și decizia Q17.

- Tabele SQLModel în `app/models/`, starea efemeră în `services/state.py`.
- `POST /api/missions`, `.../fly`, `.../refly`, `.../analyse`, `GET /api/missions/{id}` și `/stream` (SSE cu evenimentele din §9).
- `POST /api/missions/demo/{scenario}` cu seed-uri fixe pentru cele 3 scenarii din §12.

**Gata când:** un zbor complet trimite evenimentele în ordine, iar după restart starea se recuperează din SQLite.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Scheme Pydantic, mock-uri FastAPI și schelet React cu tipuri generate](05-contracte.md)

## Answer

**Ce e făcut (doar backend + `types.gen.ts` regenerat):**

- `app/models/mission.py` → tabelul `mission` (SQLModel): `id`, `settings` (JSON), `phase` (ultima fază atinsă), `status` (JSON modul → `ModuleStatus`), `demo`. „flying” nu se scrie niciodată în SQLite: un zbor în curs e progres, deci stă în memorie (Q17). După restart misiunea e la faza de dinaintea zborului.
- `app/services/state.py` → memorie per misiune: evenimentele trimise (indexul = `id:` din SSE), cadrele zburate (meta + imagine), task-ul de zbor. `sse()` reia după `Last-Event-ID` și închide stream-ul când a trimis ceva și misiunea e iar inactivă; un stream deschis pe o misiune inactivă așteaptă următoarea acțiune. `EventSource` se reconectează singur cu `Last-Event-ID` (`retry: 1000`), deci nimic nu se trimite de două ori. Un id de dinainte de restart → se trimite tot de la 0.
- `app/services/missions.py` → `create`, `to_mission`, `fly` (corutină: waypoint per masă, `frame_captured` + `frame_checked` per cadru, `cloud` sub nor, `flight_done`, apoi `agent_event` `refly_proposed` pentru mesele fără niciun cadru valid → `not_inspected`), `analyse` (mock până la 17, vezi Comments), `DEMOS` cu seed-uri fixe.
- `app/schemas/stream.py` → payload tipat per eveniment (`Waypoint`, `FrameCheck`, `Cloud`, `FlightDone`, `FindingsReady`, plus `FrameMeta`, `Alert`, `AgentEvent`). `StreamEvent` e acum o uniune discriminată după `type`, cu aceeași formă pe fir (`{type, data}`); în TS iese `WaypointEvent | FrameCapturedEvent | …`, deci `ev.data` se îngustează după `ev.type`.
- `routes/missions.py`: mock-urile sunt înlocuite. Faze: `fly` doar din `planned`, `analyse` doar din `checked`, `refly` din `checked/analysed/reviewed` și doar dacă există mese `not_inspected` (le zboară din nou fără artefacte, devin `pending`, faza → `checked`); altfel 409. `demo/{scenario}` (`normal | bad_day | explain`) recreează `demo-{scenario}` de la zero, cu `truth`. `/frames` vine din memorie, iar după restart se regenerează din seed. `thumb.png` ia imaginea din ultima misiune zburată care are cadrul (fallback: seed-ul implicit).
- `mock_data.mission()` și `stream_events()` șterse (nu mai au apelanți).
- Teste: `tests/conftest.py` (DB SQLite temporar, M-0001 creat și zburat la speed 1000) și `tests/test_missions.py` (10 teste). Cazurile fly/refly/analyse și testul de stream din `test_contracts.py` depind de fază, așa că s-au mutat în `test_missions.py`.

**Cum am verificat:**

- `cd backend && uv run pytest -q` → `146 passed, 1 skipped`; `uv run ruff check .` → `All checks passed!` (inclusiv `test_file_size.py`).
- `test_full_flight_streams_the_events_in_order` citește SSE-ul cap-coadă: id-uri 0..n-1 consecutive, 40 de waypoint-uri, fiecare `frame_captured` urmat de `frame_checked`, cadrele în ordinea zborului, `flight_done` după ultimul cadru, numărul de `cloud` egal cu cadrele sub nor, `refly_proposed` pentru masa cu `missing`.
- `test_state_survives_a_restart`: zbor → `state.clear()` + `TestClient` nou (lifespan rulat din nou) → `GET /missions/{id}` și `/frames` identice. `test_interrupted_flight_is_back_to_planned`: un zbor întrerupt de restart revine la `planned`.
- `cd frontend && npm run build` → `✓ built` după regenerarea `types.gen.ts` din `app.openapi()`.
- Live, cu `uv run fastapi dev app/main.py --port 8018`:
  - `POST /api/missions/demo/bad_day` → `demo-bad_day planned`, seed 11, toate 4 injectările; `POST .../demo-bad_day/fly` → `flying`.
  - `curl -sN .../demo-bad_day/stream` → durează 41 s la speed 1, apoi se închide singur. 207 evenimente (`retry: 1000`, apoi `id: 0` waypoint B1-R1-T1 … `id: 205` `flight_done` {frames: 74}, `id: 206` `refly_proposed` B1-R2-T4): 40 waypoint, 74 + 74 cadre, 17 cloud. `GET` → `checked`, 468 pending / 12 not_inspected.
  - `POST .../analyse` → `analysed` (463 ok, 12 not_inspected, 4 finding, 1 unsure). `curl -sN -H "Last-Event-ID: 206" .../stream` → doar `id: 207 findings_ready`, `id: 208 alert_raised`.
  - `POST .../refly` → `flying`. Stream cu `Last-Event-ID: 208` → waypoint B1-R2-T4, 2 cadre, `flight_done {frames: 2}`. `GET` → `checked`, masa e iar `pending`. `POST .../fly` → 409.
  - Server oprit și repornit → `GET .../demo-bad_day` → `checked`, cu exact aceleași statusuri. `/frames` → 74 (regenerate), `POST /missions` → `M-0001`, `thumb.png` → 200 `image/png`.

## Comments

- **Legătura cu 17 (pipeline)**, două locuri în `app/services/missions.py`:
  1. În `fly()`, pe fiecare cadru, acum se folosesc `meta.check_ok/problems` neutre din simulator. Aștept de la 17 `check.frame(meta: FrameMeta, image: np.ndarray) -> FrameMeta`, cu `check_ok`, `problems` și `gps_offset_detected` completate. Se apelează imediat după `compose.frame_image`, iar `lv.frames[meta.id]` primește meta-ul verificat. Masa fără niciun cadru `check_ok` devine deja `not_inspected` + `refly_proposed`.
  2. În `analyse()`, acum statusurile vin din `mock_data.findings()`. Aștept o singură funcție `pipeline.run(frames: list[tuple[FrameMeta, np.ndarray]], status: dict[str, ModuleStatus]) -> tuple[dict[str, ModuleStatus], list[Finding]]` (register → infer → consistency → calibrate → decision). Cadrele vin din `state.live(id).frames.values()`. Findings-urile încă nu se salvează în SQLite: `/findings`, review-urile și planul citesc tot din `mock_data`. Persistarea lor (decizii → SQLite, Q17) vine odată cu legarea lui 17.
- **Contract SSE (s-au schimbat doar tipurile):** `StreamEvent` are acum `data` tipat după `type`; JSON-ul pe fir e același. Stream-ul se închide când misiunea e inactivă, iar `EventSource` se reconectează singur cu `Last-Event-ID`. Pe `id:`, React nu trebuie să facă dedupe manual. Nota pentru 19 e în folderul de note partajate.
- **Deschis:** id-urile cadrelor (`FR-<masă>-P<n>`) nu sunt unice între misiuni, iar `/frames/{id}/thumb.png` nu știe din ce misiune e cadrul. Acum ia imaginea din ultima misiune zburată care are cadrul, ceea ce e corect cât rulează o singură misiune (demo). Varianta curată, un id unic per misiune, e o schimbare de contract și o decide omul.
- **Deschis:** conținutul scenariilor demo din `DEMOS` (seed-uri 7 / 11 / 23) e provizoriu. Hot cell-ul cu ΔT 22 K din scenariul 1 nu se poate obține cu k = 0,15 (vezi 16). Se fixează când se leagă 17 și modelul (vezi „Not yet specified” din `map.md`).
