# Planner greedy (capacitate, deplasare, grupare, motiv)

Type: task
Status: open
Owner: Tu
Țintă: H15
Blocked by: 11

## Question

Spec: §7, paragraful Planner, **fără meteo** (meteo e tichetul 28). 2 echipe × 7 h/zi, alertele critice în ziua 1, grupare pe masă/rând, `reason` pe fiecare sarcină. `GET /api/missions/{id}/plan`.

**Gata când:** planul pe 3+ zile e determinist pentru un seed fix și fiecare sarcină are motiv.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Strat de decizie: reguli YAML, pierdere, ordine de lucru, review](11-decizie.md)
