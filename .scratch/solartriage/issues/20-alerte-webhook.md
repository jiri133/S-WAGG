# Alerte, webhook cu receptor mock, jurnalul agentului

Type: task
Status: open
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
