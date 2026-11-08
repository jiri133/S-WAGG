# evaluate.py, reports/eval.json și figuri

Type: task
Status: open
Owner: Tu
Țintă: H17
Blocked by: 07, 09

## Question

Spec: §3.6 (fără testul de degradare, care e tichetul 31). Rulează pe test o singură dată: reguli → RF → ResNet18, macro-F1 pe 8 și 12, F1 per clasă, matricea de confuzie, ECE, risk–coverage, analiza erorilor, cifrele de robustețe. `GET /api/eval` servește JSON-ul.

**Gata când:** `uv run --project backend python evaluate.py` regenerează totul de la zero.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Baseline: trăsături, reguli extinse la 8 clase, Random Forest](07-baseline.md)
- [Calibrare (temperature scaling) și praguri pe severitate](09-calibrare.md)
