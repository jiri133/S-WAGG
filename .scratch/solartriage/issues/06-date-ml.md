# Date ML: descărcare Raptor, dedup, split, mapare 12→8

Type: task
Status: open
Owner: Tu
Țintă: H5
Blocked by: 01, 02

## Question

Spec: §3.1–3.2. `ml/data.py`: descarcă în `data/raptor/` (în `.gitignore`), deduplicare cu hash perceptual, split stratificat 70/15/15 cu seed fix, mapare 12→8. Scrie `ml/splits/{train,val,test}.csv`, care intră în repo.

**Gata când:** cele 3 CSV-uri există, distribuția pe clase e afișată, iar simulatorul (tichetul 16) poate citi crop-urile din test.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Python 3.15 merge cu PyTorch, ONNX Runtime și numpy?](01-python-compat.md)
- [Formatul exact al dataset-ului InfraredSolarModules](02-raptor-format.md)
