# Strat de decizie: reguli YAML, pierdere, ordine de lucru, review

Type: task
Status: open
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
