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

**Model v1 (Kaggle GPU, 20 de epoci, `ml/KAGGLE.md`), acum în `backend/artifacts/`:** cel mai bun pe val la epoca 19, **val macro-F1 0,642**, accuracy 0,758 (epoca 20: 0,622). F1 pe clase: ok 0,86, hot_cell 0,69, multi_hot 0,55, diode_substring 0,92, module_offline 0,45, soiling 0,26, shadow_vegetation 0,71, other 0,69. Verificat pe laptop: ONNX Runtime CPU pe tot val-ul (2.995 de crop-uri) dă exact macro-F1 0,6422; logits identice cu `best.pt` în PyTorch (diferență maximă 1,3e-5 pe 64 de crop-uri). `best.pt` din v1 e local în `ml/runs/v1/best.pt` (ignorat de git), pentru Grad-CAM și embedding-uri.

**De știut pentru calibrare/decizie (tichetele 09, 11):** cea mai mare confuzie e `ok` → `module_offline` (202 din 1.502 `ok` din val), deci multe alarme false de modul offline la pragul argmax. `soiling` rămâne slab (F1 0,26, doar 31 în val). Curba pe val oscilează (0,45 la epoca 11), deci selecția pe val contează.
