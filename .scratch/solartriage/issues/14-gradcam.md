# Grad-CAM pe crop

Type: task
Status: open
Owner: Tu
Țintă: H16
Blocked by: 08, 10

## Question

Spec: §3.5. `services/explain/gradcam.py` (PyTorch pe CPU, ultimul bloc conv), `GET /api/findings/{id}/gradcam.png` cu cache pe disc.

**Gata când:** heatmap-ul pentru un finding de diodă cade pe banda de 1/3.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [ResNet18 pe Kaggle → model.onnx](08-resnet-onnx.md)
- [Modelul în pipeline: /api/analyse, inferență, incertitudine](10-model-analyse.md)
