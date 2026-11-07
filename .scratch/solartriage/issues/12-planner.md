# Planner greedy (capacitate, deplasare, grupare, motiv)

Type: task
Status: resolved
Owner: Tu
Țintă: H15
Blocked by: 11

## Question

Spec: §7, paragraful Planner, **fără meteo** (meteo e tichetul 28). 2 echipe × 7 h/zi, alertele critice în ziua 1, grupare pe masă/rând, `reason` pe fiecare sarcină. `GET /api/missions/{id}/plan`.

**Gata când:** planul pe 3+ zile e determinist pentru un seed fix și fiecare sarcină are motiv.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Strat de decizie: reguli YAML, pierdere, ordine de lucru, review](11-decizie.md)

## Answer

**Ce e construit**

- `backend/app/services/decision/planner.py`: funcții pure. `plan(orders, findings, modules, start)` → `Plan`; `travel_h(a, b)` → ore de deplasare.
- Config în `decision_rules.yaml › planner`: orizont 5 zile, `capacity_h` 7 h/zi pentru `electrical` și `cleaning`, deplasare 0 / 10 / 20 min (același rând / alt rând / alt bloc), `loss_window_days: 30`.
- Pașii: criticele primele (grupate între ele) → restul după rangul din `workorders.prioritised` (scor, apoi încredere, apoi id) → după fiecare sarcină-ancoră vin sarcinile mai mici de pe aceeași masă, apoi de pe același rând → fiecare sarcină pe cea mai devreme zi în care încape, cu deplasarea socotită față de sarcina anterioară a echipei din acea zi → ce nu încape în 5 zile ajunge în `unscheduled`.
- `reason` pe fiecare sarcină: „alertă critică…” sau „urgență X, scor Y (locul N în prioritate)”, plus după caz „reinspecție după review neconcludent”, „grupat cu WO-… pe aceeași masă / același rând”, „nu mai încape la echipa … în zilele 1–N”, „deplasare N min”.
- `used_h` include deplasarea. `weather` = „fără prognoză (meteo: tichetul 28)”. `total_loss_avoided_kwh` = Σ kWh/zi × (30 − ziua + 1) pentru sarcinile planificate.
- `GET /api/missions/{id}/plan` apelează planner-ul pe ordinele de lucru din `mock_data` (deci reflectă review-urile). Planul începe a doua zi după misiune. Mock-ul `mock_data.plan()` a fost șters. Schema `Plan` e neschimbată.
- Limită: dacă orele critice depășesc 7 h, criticele umplu ziua 1 primele, iar restul trec în ziua 2 cu motivul scris (o singură echipă electrică).

**Cum am verificat**

- `cd backend && uv run pytest -q` → `88 passed`. `tests/test_planner.py` acoperă: determinismul pe seed fix (același plan, ≥ 3 zile cu sarcini), fiecare ordin planificat o dată sau trecut la neprogramate, capacitate fără suprapuneri (3 seed-uri × 60 de defecte), criticele primele în ziua 1 când încap, surplusul de critice cu motiv, motiv pe fiecare sarcină, gruparea pe același rând, timpii de deplasare și endpoint-ul prin TestClient.
- `uv run ruff check app tests` → curat. `cd frontend && npm run build` → `✓ built`.
- Endpoint-ul apelat pe serverul pornit (`fastapi dev`, :8000), prin `fetch('/api/missions/M-0001/plan')` → 200, 5 zile (2026-11-08…12). Ziua 1: WO-001 (critică) la 0 h, WO-003 la 2,33 h și WO-002 la 3,17 h, fiecare cu „deplasare 20 min”, plus WO-005 la curățenie. `used_h` electrical 4,67 h, `unscheduled` [], 50,6 kWh evitați. După `POST /api/findings/F-004/review {"decision":"confirmed"}`, WO-004 apare la 5 h în ziua 1 (`used_h` 7,0), deci planul se reface după review.
