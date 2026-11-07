# Baseline: trăsături, reguli extinse la 8 clase, Random Forest

Type: task
Status: open
Owner: Tu
Țintă: H7
Blocked by: 06

## Question

Spec: §3.3.

- `backend/app/services/baseline/features.py` și `rules_classifier.py`: `classify()` din PoC portat pe intensitate, extins la 8 clase, cu praguri ajustate pe train.
- RF în `ml/`, pe aceleași trăsături.

**Gata când:** există tabelul macro-F1 pe val pentru ambele baseline-uri.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Date ML: descărcare Raptor, dedup, split, mapare 12→8](06-date-ml.md)
