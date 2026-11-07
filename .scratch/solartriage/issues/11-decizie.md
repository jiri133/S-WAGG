# Strat de decizie: reguli YAML, pierdere, ordine de lucru, review

Type: task
Status: resolved
Owner: Tu
Țintă: H12
Blocked by: 05

## Question

Spec: §7 și §8.

- `backend/config/decision_rules.yaml`, `loss.yaml`, `pvgis_bucharest.json` (descărcat o dată de pe PVGIS și salvat).
- `services/decision/rules.py`, `loss.py`, `workorders.py`.
- `POST /api/findings/{id}/review` reface ordinele de lucru. `GET .../work-orders?format=csv` și `labels.csv`.

**Gata când:** finding-urile au urgență, pierdere, echipă, piesă și `rule_applied`, iar CSV-ul se descarcă.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Scheme Pydantic, mock-uri FastAPI și schelet React cu tipuri generate](05-contracte.md)

## Answer

Făcut pe branch-ul `claude/11-decizie-9bf690`.

**Fișiere**
- `backend/config/decision_rules.yaml`: regula de siguranță (`hot_cell`/`multi_hot`/`diode_substring` cu ΔT ≥ 20 K → `critical` + alertă), urgența de bază, ponderile scorului (critical 10 · high 5 · medium 2 · low 1), pe clasă echipă/piesă/ore/verificare sugerată, plus `reinspection` (0,5 h, electrical). Am adăugat și `ok` (low, reverificare), pentru un `ok` nesigur care ajunge în coadă.
- `backend/config/loss.yaml`: 0,55 kWp, fracțiile din §7, `ok` = 0, preț fix 0,60 RON/kWh.
- `backend/config/pvgis_bucharest.json`: răspunsul brut PVGIS v5.3, descărcat o dată pe 2026-11-07 de la `https://re.jrc.ec.europa.eu/api/v5_3/PVcalc?lat=44.43&lon=26.10&peakpower=1&loss=14&optimalangles=1&outputformat=json` (SARAH3, 2005–2023, înclinare optimă 36°, pierderi sistem 14 %). **E_y = 1.297,9 kWh/kWp/an** (spec-ul zicea ~1.350). Se folosește `E_d` lunar.
- `backend/app/services/decision/rules.py` (`apply`, `score`), `loss.py` (`loss_kwh_day`, `loss_ron_day`, `daily_yield`), `workorders.py` (`finding_fields`, `prioritised`, `work_orders`). Funcții pure, YAML-ul citit o dată.
- `rule_applied` citează regula: `decision_rules.yaml › safety: hot_cell cu ΔT 22.4 K ≥ 20 K → critical + alertă · verificare: …` sau `decision_rules.yaml › classes.<cls>: urgență de bază <u> · verificare: …`.
- Rute: `GET /missions/{id}/findings` sortat după scor (la egalitate, încrederea), `POST /findings/{id}/review` salvează decizia și ordinele se refac la citire (confirmed → ordin, rejected → fără ordin, inconclusive → ordin cu `ticket_status: "reinspection"`, fără piesă, 0,5 h), `GET /missions/{id}/work-orders?format=json|csv` (coloanele = câmpurile `WorkOrder`, și pentru listă goală), `GET /missions/{id}/labels.csv` (`finding_id,module_id,predicted,review,note`).
- `mock_data.py` ține acum doar detecțiile brute (modul, clasă, baseline, ΔT, unsure). Câmpurile de decizie vin din stratul real, luna 11 pentru yield. Review-urile stau în memorie (`mock_data._reviews`) până la tichetul de stare/SQLite. Pipeline-ul, SSE-ul și planul rămân mock-uri.
- Dependență nouă: `pyyaml` (pe lista permisă).

**Verificare**

`cd backend && uv run ruff check app tests` → `All checks passed!`
`cd backend && uv run pytest -q` → `56 passed in 3.03s` (24 noi în `tests/test_decision.py`: critical la 20 K pentru cele 3 clase de risc, 19,9 K rămâne medium, soiling la 35 K rămâne low, urgență/echipă/piesă/ore pentru toate 7 clasele, scor, yield PVGIS plauzibil, formula pierderii, unsure exclus până la confirmare, rejected fără ordin, inconclusive → reinspecție, departajare după încredere, endpoint-urile de findings/review/404/CSV/labels).
`cd frontend && npm ci && npm run build` → `✓ built in 226ms`.

Endpoint-urile apelate cap-coadă cu `TestClient(app)` (`PYTHONPATH=. uv run python smoke.py`):

```
GET findings:
  F-003 module_offline   unsure=False high     1.171 kWh/d 0.7 RON/d score=5.855 | decision_rules.yaml › classes.module_offline: urgență de bază high
  F-002 diode_substring  unsure=False high     0.387 kWh/d 0.23 RON/d score=1.935 | decision_rules.yaml › classes.diode_substring: urgență de bază high
  F-001 hot_cell         unsure=False critical 0.035 kWh/d 0.02 RON/d score=0.35 | decision_rules.yaml › safety: hot_cell cu ΔT 22.4 K ≥ 20 K → critical + alertă
  F-004 multi_hot        unsure=True  medium   0.117 kWh/d 0.07 RON/d score=0.234 | decision_rules.yaml › classes.multi_hot: urgență de bază medium
  F-005 soiling          unsure=False low      0.094 kWh/d 0.06 RON/d score=0.094 | decision_rules.yaml › classes.soiling: urgență de bază low
work-orders before review: [('F-003', 'pending'), ('F-002', 'pending'), ('F-001', 'pending'), ('F-005', 'pending')]
POST /api/findings/F-004/review confirmed -> 200 confirmed
POST /api/findings/F-001/review rejected -> 200 rejected
POST /api/findings/F-002/review inconclusive -> 200 inconclusive
work-orders after review: [('F-003', 'pending'), ('F-002', 'reinspection'), ('F-004', 'pending'), ('F-005', 'pending')]
GET work-orders?format=csv -> 200 text/csv; charset=utf-8 attachment; filename="work-orders-M-0001.csv"
id,finding_id,module_id,string,inverter,fault,part,crew,est_hours,urgency,evidence_url,created_at,ticket_status
WO-003,F-003,B2-R1-T2-M11,B2-R1-S1,INV-2.1,module_offline,conectori,electrical,0.5,high,/api/findings/F-003/crop.png,2026-11-07T10:00:00Z,pending
WO-002,F-002,B1-R4-T1-M03,B1-R4-S1,INV-1.4,diode_substring,,electrical,0.5,high,/api/findings/F-002/crop.png,2026-11-07T10:00:00Z,reinspection
WO-004,F-004,B2-R3-T4-M05,B2-R3-S2,INV-2.3,multi_hot,modul,electrical,2.0,medium,/api/findings/F-004/crop.png,2026-11-07T10:00:00Z,pending
WO-005,F-005,B2-R5-T1-M09,B2-R5-S1,INV-2.5,soiling,,cleaning,0.25,low,/api/findings/F-005/crop.png,2026-11-07T10:00:00Z,pending
GET labels.csv -> 200 text/csv; charset=utf-8
finding_id,module_id,predicted,review,note
F-001,B1-R2-T3-M07,hot_cell,rejected,smoke
F-002,B1-R4-T1-M03,diode_substring,inconclusive,smoke
F-003,B2-R1-T2-M11,module_offline,,
F-004,B2-R3-T4-M05,multi_hot,confirmed,smoke
F-005,B2-R5-T1-M09,soiling,,
```

**De reținut pentru alte tichete**
- **Scorul după formula din §7 pune un hot_cell `critical` sub un modul offline**, pentru că pierderea lui e mică (0,035 kWh/zi în noiembrie). E conform spec-ului: alertele critice intră în ziua 1 prin planner (tichetul 12) și prin alertă (tichetul 20). **Decis de om (2026-11-07): rămâne formula din spec**, fără sortare după urgență și fără pondere mărită.
- Alerta: `rules.apply(cls, ΔT)["alert"]` (tichetul 20). `Finding` nu are câmp de alertă, deci n-am adăugat unul.
- Reinspecția e un `WorkOrder` cu `ticket_status: "reinspection"`. N-am inventat un tip nou.
- `rejected` rămâne în lista de findings cu `review: "rejected"` (necesar pentru labels.csv și acordul om–model) și dispare doar din ordine.
- Review-urile sunt în memorie, nu în SQLite. Le mută tichetul de stare.
