# Calibrare (temperature scaling) și praguri pe severitate

Type: task
Status: open
Owner: Tu
Țintă: H13
Blocked by: 08

## Question

Spec: §3.4. `ml/calibrate.py` → `backend/artifacts/temperature.json` și `thresholds.json` (precizie ≥ 95% pe ce trece automat, praguri pe grup de severitate). ECE și reliability diagram înainte/după.

**Gata când:** fișierele există și ECE scade.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [ResNet18 pe Kaggle → model.onnx](08-resnet-onnx.md)
