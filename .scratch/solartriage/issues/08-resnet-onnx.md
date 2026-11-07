# ResNet18 pe Kaggle → model.onnx

Type: task
Status: resolved
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

## Answer

**Cod:** `ml/train.py`, `ml/export_onnx.py`, `ml/notebooks/train_kaggle.ipynb`, ghidul `ml/KAGGLE.md`, testul `ml/tests/test_train_export.py`. Proiectul `ml/` are acum și `torch 2.15`, `torchvision 0.29`, `onnx`, `onnxruntime 1.31` (Python 3.14) și `pytest` ca dev.

**Cum e făcut (§3.3):** ResNet18 ImageNet, crop gri replicat pe 3 canale, 24×40 → 64×96 (W×H), class weights + oversampling ușor (ambele ∝ 1/√n_clasă, deci împreună echilibrează complet), augmentări flip H/V, ±0,1 luminozitate, zgomot σ=0,02, fără rotație. AdamW 1e-3 + OneCycle, selecție pe macro-F1 pe val. Split-ul test nu e citit. Flag-uri: `--device cuda|cpu`, `--epochs` (implicit 20), `--out`, `--limit` (smoke), `--no-pretrained` (teste fără rețea).

**Contract ONNX (important pentru tichetul 10):** preprocesarea e **în graf**. Intrarea `crop` are forma `(batch, 1, 40, 24)` float32 = pixel / 255, fără normalizare în backend. Ieșirea `logits` (8, fără softmax), ordinea claselor e în `backend/artifacts/model_meta.json`. Batch dinamic, restul formei fix. Export cu exportatorul TorchScript (`dynamo=False`), opset 17, ca să nu fie nevoie de `onnxscript`.

**Repo privat:** `git ls-remote https://github.com/jiri133/S-WAGG` fără autentificare → `could not read Username`. Deci notebook-ul nu clonează; `ml/` se încarcă ca dataset Kaggle din `git archive --format=zip -o solartriage-ml.zip HEAD ml`. Notebook-ul descarcă doar imaginile (`data.download()` + `data.extract()`), split-urile vin din repo.

**Cum am verificat:**
- `cd ml && uv run pytest -q` → **2 passed** (57 s): o epocă pe 64 de crop-uri → `best.pt` → `model.onnx` → ONNX Runtime CPU pe un crop real din val, logits egale cu PyTorch (rtol 1e-3).
- `uv run --project ml python ml/train.py --device cpu --epochs 1 --limit 512` cu greutăți ImageNet, apoi `ml/export_onnx.py` → `model.onnx` 44,7 MB, rulat cu onnxruntime pe `images/0.jpg` → ieșire (1, 8).
- Notebook-ul simulat local: zip-ul din `git archive` dezarhivat ca `/kaggle/input`, toate celulele de cod rulate cu căile schimbate și `cuda`→`cpu --limit 128` → în `working/` apar `best.pt`, `model.onnx`, `model_meta.json`, `val_report.json`.
- Antrenare completă pe CPU (Ryzen AI 7 350): **~85 s/epocă**. 1 epocă → val macro-F1 0,256; 4 epoci → 0,253 / 0,474 / 0,533 / **0,549** (accuracy 0,611). F1 pe clase la epoca 4: ok 0,71, hot_cell 0,63, multi_hot 0,41, diode_substring 0,86, module_offline 0,26, soiling 0,26, shadow_vegetation 0,58, other 0,69.
- `cd backend && uv run pytest -q` → 32 passed. `ruff check` pe fișierele noi → curat.

**Model v0 în repo:** `backend/artifacts/model.onnx` (cele 4 epoci CPU de mai sus, val macro-F1 **0,549**) + `model_meta.json` + `val_report.json`. Se încarcă cu ONNX Runtime pe CPU, input `['batch', 1, 40, 24]`; `images/0.jpg` (module_offline) → `module_offline`. Integrarea (tichetul 10) poate începe pe el.

**Rămâne de făcut de om:** **v1** pe GPU-ul Kaggle, 20 de epoci, după `ml/KAGGLE.md`. Apoi se înlocuiesc cele 3 fișiere din `backend/artifacts/` și se notează aici macro-F1 pe val. `best.pt` din v1 se păstrează local (Grad-CAM, embedding-uri), nu intră în git. Neverificat: rularea reală pe Kaggle (GPU T4, versiunea lor de torch și dacă au `onnx` preinstalat; notebook-ul îl instalează doar dacă lipsește).
