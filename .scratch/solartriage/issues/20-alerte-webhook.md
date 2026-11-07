# Alerte, webhook cu receptor mock, jurnalul agentului

Type: task
Status: resolved
Owner: Alina
Țintă: H14
Blocked by: 11, 18

## Question

Spec: §8. `services/decision/alerts.py`, `POST` webhook per ordin sau alertă (3 reîncercări, totul logat), `/api/mock/ticketing`, evenimentele `alert_raised` și `agent_event` pe SSE, `GET /api/missions/{id}/events`.

**Gata când:** un hot cell ≥ 20 K produce o alertă, un tichet în receptorul mock și o intrare în jurnal.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Strat de decizie: reguli YAML, pierdere, ordine de lucru, review](11-decizie.md)
- [Starea misiunii: SQLite, SSE, endpoint-urile de misiune](18-stare-sse.md)

## Answer

**Ce e făcut (doar backend; frontend neschimbat):**

- `app/services/decision/alerts.py`:
  - `raise_alerts(findings, raised_at)` → un `Alert` per finding care atinge regula de siguranță, folosind direct `rules.apply(...)["alert"]` (pragul de 20 K și clasele vin din `decision_rules.yaml`). ID stabil `AL-<finding>` (`AL-001` pentru `F-001`), mesaj în română cu ΔT cu virgulă zecimală, `raised_at` ISO UTC.
  - `send(payload, url=None)` → POST către `settings.webhook_url`, 3 încercări; fiecare încercare (`attempt i/3`) și fiecare eșec se loghează (`warning`), succesul `info`, eșecul final `error`. Transportul e `_post(url, payload)`, funcție de modul, deci testele o înlocuiesc fără rețea.
  - `save/for_mission/acknowledge/clear`: alertele misiunii stau în tabelul SQLite `alert` (PK compus `mission_id` + `id`), deci trec restartul (Q17); `save` înlocuiește alertele misiunii, iar `missions.create` curăță rândurile vechi când un demo e recreat.
- `app/models/alert.py` → `AlertRow`; `app/core/config.py` → `webhook_url`, implicit `http://localhost:8000/api/mock/ticketing`.
- `missions.analyse` e acum `async` și: emite `findings_ready`, derivă alertele, le salvează, emite `alert_raised` pe SSE și în jurnal (`alert_raised`), trimite webhook-ul și jurnalizează rezultatul (`webhook_sent` / `webhook_failed`). Pentru fiecare ordin de lucru (`workorders.work_orders`) jurnalizează `work_order_created` și trimite webhook-ul, tot cu rezultat în jurnal. `analyse` e async ca POST-ul către același proces FastAPI să poată fi servit cât `httpx` așteaptă (fără deadlock pe event loop).
- `state.Live.journal` → jurnalul misiunii în memorie (ca evenimentele, Q17); `_journal()` îl scrie și pe SSE ca `agent_event`. În `fly` intră acum în jurnal și `frame_rejected` (cadrele respinse de data check) și `refly_proposed`.
- `routes/actions.py`: `GET /missions/{id}/alerts` citește alertele misiunii din SQLite; `GET /missions/{id}/events` citește jurnalul misiunii; `POST /alerts/{id}/ack` marchează alerta în SQLite (rămâne fallback pe mock-ul AL-001 cât timp nicio misiune nu a fost analizată, ca `test_contracts` să aibă ce confirma). Forma endpoint-urilor din §9 e neschimbată.
- `mock_data.events()` șters (nu mai are apelanți după mutarea pe jurnalul real).

**Ce s-a schimbat intenționat în teste:**

- `test_missions.py`: după `analyse`, streamul are acum `findings_ready`, `alert_raised` și 10 `agent_event` (2 pentru alertă + 2 × 4 ordine), deci aserțiunile verifică primele două tipuri și numărul de `agent_event`, nu lista exactă de 2 evenimente.
- `conftest.py`: fixture autouse care înlocuiește `alerts._post` cu un no-op, ca niciun test să nu iasă în rețea.
- `test_alerts.py` (10 teste): prag 20 K și finding non-critic fără alertă; alertă + tichet în `/api/mock/ticketing`; 3 încercări + log pentru senderul care pică, o singură încercare pentru succes; jurnal cu `alert_raised` + `work_order_created`; `webhook_failed` jurnalizat; `alert_raised` pe SSE; ack; alertele trec restartul.

**Cum am verificat:**

- `cd backend && uv run pytest -q` → `184 passed, 1 skipped in 37.05s` (toată suita, inclusiv `test_file_size.py`).
- `cd backend && uv run ruff check .` → `All checks passed!`.
- `cd frontend && npm run build` → `✓ built in 418ms` (fără modificări de schemă API, `types.gen.ts` neschimbat).
- Live, server real pe portul 8019 cu `WEBHOOK_URL=http://127.0.0.1:8019/api/mock/ticketing` (implicitul e 8000):
  - `POST /api/missions {"speed": 200}` → `M-0001 planned`; `POST .../fly` → `flying`; `GET /missions/M-0001` → `checked`.
  - `POST .../analyse` → `200 analysed`.
  - `GET /api/missions/M-0001/alerts` → `[{"id":"AL-001","finding_id":"F-001","level":"critical","message":"hot_cell cu ΔT 22,4 K pe B1-R2-T3-M07 (≥ 20 K)","raised_at":"2026-11-07T19:44:12Z","acknowledged":false}]`.
  - `GET /api/missions/M-0001/events` → 20 intrări: 9 `frame_rejected`, 1 `refly_proposed`, `alert_raised` (AL-001), `webhook_sent` (AL-001) și, pentru fiecare din cele 4 ordine, `work_order_created` + `webhook_sent`.
  - `GET /api/mock/ticketing` → 5 tichete: `['AL-001','WO-003','WO-002','WO-001','WO-005']`; tichetul AL-001 conține alerta întreagă.

**Deschis / de știut:**

- Jurnalul rămâne în memorie (Q17: progresul în memorie); după restart `GET /events` e gol, dar alertele (SQLite) rămân — testat în `test_alerts_survive_a_restart`.
- `analyse` încă folosește finding-urile mock (F-001 e hot cell-ul cu ΔT 22,4 K); legarea pipeline-ului real rămâne pe tichetul 17/21.
- ID-urile de alertă sunt derivate din finding (`AL-001`), deci două misiuni au același ID; `ack` marchează toate rândurile cu acel ID. Endpoint-ul de ack nu are misiune în path (§9), deci asta e comportamentul posibil.
