# Prioritate și urgență din ML (risc așteptat), ordine de lucru automate

Type: task
Status: claimed
Owner: Tu
Țintă: H18
Blocked by: 11, 12, 32

## Question

Decizia omului: „ML și pentru urgență/scor” și „Da, așa” la planul de mai jos ([ADR 0001](../../../docs/adr/0001-prioritate-din-risc-asteptat.md)).

1. **Scor = risc așteptat:** `scor = Σ_c p(c) × pondere_urgență(c) × pierdere_kWh(c)`, cu `p` = `Finding.prediction.probs` (calibrate), ponderile din `decision_rules.yaml`, pierderile din `loss.yaml`; `ok` contribuie 0.
2. **Urgență din ML:** clasa cu contribuția cea mai mare dă urgența (regulile YAML pe clasă). Regula ΔT ≥ 20 K rămâne plasă de siguranță: critical + alertă indiferent de model. `alerts.py` (tichetul 20) nu se atinge, doar intrarea `rules.apply(cls, ΔT)["alert"]`.
3. **Ordine automate:** toate finding-urile primesc ordin fără review; la cele `unsure` ordinul e „verifică și repară”, cu încrederea modelului în motiv. Review: respins scoate ordinul, confirmat îl păstrează fără eticheta de verificare, neconcludent → reinspecție.
4. `rule_applied` explică pe scurt calculul și de unde vine urgența.
5. Planner-ul (12) se schimbă doar cât trebuie; criticele rămân în ziua 1.

**Gata când:** teste unitare (scor așteptat 60% ok / 40% diodă între 0 și diodă sigură, ordine stabilă, urgență din contribuția maximă, ΔT ≥ 20 K → critical cu model sigur pe ok, ordin automat pentru unsure, respins → fără ordin); backend pytest + ruff, `npm run build`, `npx playwright test` verzi; endpoint-urile apelate cu serverul pornit.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Strat de decizie: reguli YAML, pierdere, ordine de lucru, review](11-decizie.md)
- [Planner greedy (capacitate, deplasare, grupare, motiv)](12-planner.md)
- [Macro-F1 mai mare fără reantrenare: TTA cu flip-uri + bias pe clase](32-macro-f1.md)

## Answer

**Ce s-a schimbat (FastAPI, `backend/app/services/decision/` + `decision_rules.yaml`):**

- `workorders.contributions(probs, month)` = `p(c) × rules.weight(c) × loss.loss_kwh_day(c, month)`. `finding_fields` dă `score = Σ contribuții`, `loss_kwh_day` = pierderea așteptată `Σ p(c) × kWh(c)` (RON din ea), `urgency` din clasa cu contribuția maximă (la egalitate, probabilitatea mai mare). Echipa, piesa și durata urmează clasa prezisă (`prediction.cls`), deci `WorkOrder.fault` rămâne clasa modelului.
- `rules.urgency(cls, ΔT)` e regula de urgență. **Siguranța trece acum doar după ΔT** (am scos `safety.classes` din YAML) și trimite ordinul la `safety.crew: electrical`. `rules.apply` păstrează cheia `alert` pentru `alerts.py`, deci alerta apare și pe un ΔT ≥ 20 K prezis ok. `rules.score` a fost înlocuit de `rules.weight`.
- `prioritised`: criticele primele, apoi scor, încredere, id (ordine stabilă). Criticele trebuie puse explicit primele, pentru că riscul așteptat nu mai folosește ponderea critical (F-001: scor 0,148).
- `work_orders`: fiecare finding nerespins are ordin; `unsure` fără review → `ticket_status = "verify_and_repair"`; confirmat → `pending`; neconcludent → reinspecție.
- `planner._reason` adaugă „verifică și repară: modelul e sigur 55% pe multi_hot” la ordinele de verificare. Restul planner-ului e neschimbat.
- `rule_applied`, de exemplu: `risc așteptat: 0,55 multi_hot × pondere 2 × 0,117 kWh + 0,01 module_offline × pondere 5 × 1,171 kWh + 0,01 diode_substring × pondere 5 × 0,387 kWh + … = scor 0,210; urgență din multi_hot (decision_rules.yaml › classes.multi_hot: medium) · verificare: …` (primii 3 termeni, apoi „+ …”).
- Mock: restul probabilității merge acum pe `ok` (0,01 pe celelalte clase), nu uniform. Cu restul uniform (0,064 pe fiecare), `module_offline` ar fi dominat riscul la F-004.
- **Fără câmpuri noi în scheme**; `types.gen.ts` nu s-a regenerat. `ticket_status` e `str`, iar `verify_and_repair` e doar o valoare nouă.
- Frontend: doar `e2e/plan.spec.ts`, rescris ca „Respinge scoate ordinul din plan” (Confirmă → WO-004 vizibil, Respinge → dispare). Nicio componentă React atinsă.
- Teste ajustate: `test_alerts` (6 webhook-uri: o alertă + 5 ordine), `test_missions` (12 `agent_event`), iar scenariul din `test_planner` pune ΔT 25 K doar pe clasele de risc, cum spunea deja docstring-ul. Altfel soiling/offline la 25 K deveneau critice și depășeau ziua 1.

**Cum am verificat:**

- `cd backend && uv run pytest -q` → `197 passed, 1 skipped` (inclusiv `test_file_size.py`). Teste noi în `test_decision.py`: `test_expected_risk_sits_between_ok_and_a_sure_fault`, `test_urgency_comes_from_the_largest_contribution`, `test_safety_makes_critical_even_when_the_model_is_sure_of_ok`, `test_safety_rule_trips_at_20k_whatever_the_class`, `test_priority_order_is_stable`, `test_unsure_finding_gets_a_verify_order_without_review`, `test_rejected_finding_gets_no_order`. În `test_planner.py`: `test_unsure_order_is_planned_as_verify_and_repair`.
- `cd backend && uv run ruff check .` → `All checks passed!`
- `cd frontend && npm ci && npm run build` → build OK; `npx playwright test` → `3 passed`.
- Server pornit (`fastapi dev` din `.claude/launch.json`, pe :8003). `GET /api/missions/M-0001/findings` e lista de priorități (nu există `/findings/prioritised`):
  ```
  F-001 hot_cell        critical 0.148  … safety: ΔT 22,4 K ≥ 20 K → critical + alertă, indiferent de model
  F-003 module_offline  high     5.47   … urgență din module_offline (classes.module_offline: high)
  F-004 multi_hot unsure medium  0.21   … urgență din multi_hot (classes.multi_hot: medium)
  ```
  `GET /api/missions/M-0001/work-orders` → 5 ordine, inclusiv `WO-004 multi_hot medium verify_and_repair`. `GET /api/missions/M-0001/plan` → toate 5 în ziua 1, `unscheduled []`; `WO-004`: „urgență medium, scor 0.21 (locul 4 în prioritate); verifică și repară: modelul e sigur 55% pe multi_hot; deplasare 20 min”.

**De urmărit:** cu probabilitățile reale, 1% pe `module_offline` (pierdere 1,0 × pondere 5) poate ridica la high un modul sigur pe `other`. E efectul riscului așteptat și e notat în ADR. Analiza misiunii încă folosește finding-urile mock (factorul k, Alina). Rămâne `claimed` până verifică omul.
