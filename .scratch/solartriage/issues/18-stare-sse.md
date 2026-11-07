# Starea misiunii: SQLite, SSE, endpoint-urile de misiune

Type: task
Status: claimed
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
