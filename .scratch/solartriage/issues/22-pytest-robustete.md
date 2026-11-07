# pytest: cele 6 cazuri de robustețe și regula de 30 KB

Type: task
Status: claimed
Owner: Alina
Țintă: H18
Blocked by: 17

## Question

Spec: §6 și §11. `backend/tests/test_robustness.py` (cele 6 cazuri), `test_contracts.py`, `test_file_size.py` (niciun fișier sursă peste 30.720 bytes, cu excepțiile din §11).

**Gata când:** `uv run pytest -q` trece pe ambele laptopuri.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Pipeline: data check, înregistrare GPS, consistency check](17-pipeline-check.md)
