# Antrenarea ResNet18 pe GPU-ul Kaggle (tichetul 08)

Repo-ul e privat, deci notebook-ul nu face `git clone`. Încarci folderul `ml/` ca dataset Kaggle.
Totul durează ~15 minute, din care antrenarea ~5–10 minute pe T4.

## 1. Cont (o singură dată)

1. Deschide <https://www.kaggle.com> → **Register** (sau Sign in cu Google).
2. Click pe avatar (dreapta sus) → **Settings**.
3. La **Phone Verification** → **Verify** → numărul tău → codul primit prin SMS.
   Fără verificare nu ai nici GPU, nici Internet în notebook.

## 2. Pregătește codul (pe laptop, din rădăcina repo-ului)

```powershell
git archive --format=zip -o solartriage-ml.zip HEAD ml
```

Arhiva are doar fișierele din git (`train.py`, `data.py`, `export_onnx.py`, `splits/*.csv`, notebook-ul), fără `.venv` și fără imagini. Fă commit înainte, altfel arhiva nu are ultimele modificări.

## 3. Încarcă codul ca dataset

1. Pe Kaggle, stânga → **Datasets** → **+ New Dataset**.
2. Trage `solartriage-ml.zip` în fereastră. Titlu: `solartriage-ml`. Lasă **Private**.
3. **Create**. Așteaptă până scrie că s-a procesat.

## 4. Notebook-ul

1. Stânga → **Code** → **+ New Notebook**.
2. Meniu **File** → **Import Notebook** → alege `ml/notebooks/train_kaggle.ipynb` din repo → **Import**.
3. Panoul din dreapta (dacă nu se vede: iconița cu săgeată din dreapta sus) → **Session options**:
   - **Accelerator** → **GPU T4 x2** (sau T4) → **Turn on GPU**.
   - **Internet** → **On**.
4. Tot în dreapta, **Input** → **+ Add Input** → **Your Work** / **Datasets** → `solartriage-ml` → **+**.
5. Opțional: în prima celulă de cod, `EPOCHS = 20`. Pentru un v0 rapid pune `1`.
6. Sus: **Run All**. În celula de antrenare apare câte o linie `epoca N: loss …, val macro-F1 …`.
   Dacă prima celulă dă `AssertionError: Settings → Accelerator → GPU T4`, GPU-ul nu e pornit (pasul 4.3).

## 5. Descarcă rezultatele

1. Dreapta → **Output** (`/kaggle/working`). Apar: `model.onnx` (~45 MB), `model_meta.json`, `best.pt`, `val_report.json`.
2. La fiecare fișier: **⋮** → **Download**. Păstrează `best.pt` (greutățile PyTorch, pentru Grad-CAM și embedding-uri); nu intră în git.
3. Ultima celulă afișează macro-F1 pe val, total și pe clase. Notează cifra în tichetul 08.

## 6. Pune modelul în repo (PowerShell, din rădăcina repo-ului)

```powershell
Copy-Item "$HOME\Downloads\model.onnx", "$HOME\Downloads\model_meta.json", "$HOME\Downloads\val_report.json" backend\artifacts\
uv run --project ml python -c "import onnxruntime as o; print(o.InferenceSession('backend/artifacts/model.onnx').get_inputs()[0].shape)"
git add backend/artifacts
git commit -m "feat(ml): model v1 de pe Kaggle"
```

A doua comandă trebuie să afișeze `['batch', 1, 40, 24]`.

## Dacă ceva nu merge

- **Exportul ONNX pică pe Kaggle:** descarcă doar `best.pt` și exportă pe laptop:
  `uv run --project ml python ml/export_onnx.py --ckpt <cale>\best.pt`
- **Fără GPU (cota săptămânală consumată):** același cod pe CPU-ul laptopului, ~2 min/epocă:
  `uv run --project ml python ml/train.py --device cpu --epochs 10`, apoi `ml/export_onnx.py`.
