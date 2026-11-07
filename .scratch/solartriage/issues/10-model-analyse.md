# Modelul în pipeline: /api/analyse, inferență, incertitudine

Type: task
Status: open
Owner: Tu
Țintă: H12
Blocked by: 05, 08

## Question

Spec: §5 pașii 3 și 5. Modelul se încarcă în `lifespan`, plus `services/pipeline/infer.py`, `calibrate.py` și `POST /api/analyse` (un crop → `Prediction`).

**Gata când:** pipeline-ul misiunii folosește modelul în locul baseline-ului, iar `unsure` apare conform pragurilor.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Scheme Pydantic, mock-uri FastAPI și schelet React cu tipuri generate](05-contracte.md)
- [ResNet18 pe Kaggle → model.onnx](08-resnet-onnx.md)
