# ResNet18 pe Kaggle → model.onnx

Type: task
Status: claimed
Owner: Tu
Țintă: v0 H6, v1 H12
Blocked by: 06

## Question

Spec: §3.3. `ml/train.py`, `ml/notebooks/train_kaggle.ipynb`, `ml/export_onnx.py`. Agentul scrie codul, tu rulezi notebook-ul pe GPU-ul Kaggle și pui `model.onnx` în `backend/artifacts/`.

V0 (o epocă) până la H6, ca integrarea să înceapă. V1 complet până la H12.

**Gata când:** `model.onnx` se încarcă cu ONNX Runtime pe CPU, iar macro-F1 pe val e notat.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Date ML: descărcare Raptor, dedup, split, mapare 12→8](06-date-ml.md)

## Comments

- 2026-11-07 · Tu: fără GCP. `ml/train.py` merge identic pe Kaggle GPU și pe CPU-ul laptopului, cu `--device cuda|cpu` (rezervă: Ryzen AI 7 350, ~1–2 min/epocă estimat).
