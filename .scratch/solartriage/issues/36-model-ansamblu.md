# Model mai bun: ansamblu de două ResNet18 de pe Kaggle (mai puține „nesigure”)

Type: task
Status: resolved
Owner: Tu
Țintă: după H20
Blocked by: 32

## Question

Decizia omului: „Model mai bun”, ca să ajungă mai puține finding-uri în coada „nesigure”. Antrenarea se face pe Kaggle, cu notebook-ul v2 al Alinei (`ml/notebooks/train_v2_kaggle.ipynb`): 4 rulări (control v1, label smoothing, augmentări cu glare și blur, al doilea seed). Totul se alege doar pe val, iar testul se folosește o singură dată, prin `evaluate.py`. Interfața ONNX rămâne aceeași: `crop` (batch,1,40,24) → `logits` (batch,8).

## Answer

**Pe Kaggle (rularea omului, output în `Smarthack/kaggle/`), după TTA + bias pe val:** v2_ls 0,7309 · v2_aug_seed123 0,7307 · v1_control 0,7265 · v2_aug 0,7239. Baseline-ul v1.1 avea 0,7194.

**Exportul de pe Kaggle (doar v2_ls) nu l-am pus în aplicație.** Are macro-F1 mai mare, dar label smoothing îl face mai puțin sigur: pe val trec automat 57,4% (v1.1: 59,5%), iar shadow_vegetation și other ajung mereu la inginer.

**Ansamblul, ales pe val din toate combinațiile de membri, cu și fără bias:**

| pe val | macro-F1 | trec automat | precizie |
|---|---|---|---|
| v1.1 (actual) | 0,719 | 59,5% | 95,6% |
| v2_ls singur + bias | 0,730 | 60,9% | 95,7% |
| **v2_ls + v2_aug_seed123 + bias** | **0,744** | **64,0%** | 95,9% |
| v1 + v2_ls + v2_aug_seed123 + bias | 0,742 | 64,6% | 96,1% |

Am ales varianta cu 2 membri: cu 3, ONNX-ul ar avea ~128 MB, peste limita GitHub de 100 MB, iar inferența ar fi mai lentă.

**Ce s-a construit:**
- `ml/export_onnx.py › Ensemble` / `export_ensemble`: media softmax pe 4 flip-uri și pe membri, log, + bias, într-un singur `model.onnx` (89,4 MB). Interfața e neschimbată, iar `model_meta.json › members` listează membrii.
- `ml/ensemble.py --ckpt … --ckpt … [--install]`: bias-ul ales pe val, comparația cu modelul actual și instalarea doar dacă îl bate la macro-F1 **și** la acoperire. Apoi rulează `ml/calibrate.py` (T = 0,76; ansamblul e puțin prea modest, nu prea sigur). Verificat: |ONNX − numpy| = 1,4e-5 pe val.
- `best.pt` (Grad-CAM, cazuri similare) = membrul **v2_ls**. Pe 250 de diode din val, căldura Grad-CAM pe banda diodei: v1 0,478, v2_ls 0,446, v2_aug 0,455, v2_aug_seed123 0,393 (uniform: 0,33). Pe toate crop-urile din `tests/fixtures`, v2_ls prezice aceeași clasă ca ansamblul. `embeddings.npy` e refăcut cu `ml/build_index.py`.
- Greutățile membrilor sunt în `ml/runs/kaggle_v2/` (ignorat de git).

**Pe test (`PYTHONUTF8=1 uv run --project backend python evaluate.py`, o singură rulare):**
- macro-F1 0,706 → **0,729**, accuracy 0,825 → 0,850;
- automat **60,1% → 64,5%**, la precizie 96,0% → 95,7%;
- F1 pe clase: ok 0,94 → 0,96, module_offline **0,71 → 0,83**, shadow_vegetation 0,72 → 0,77, other 0,68 → 0,73, multi_hot 0,49 → 0,51, hot_cell 0,70 (la fel), diode 0,97 (la fel), soiling 0,44 → 0,36 (doar 30 de exemple);
- ECE 0,106 → 0,031 (v1.1: 0,015);
- degradarea e mai robustă: zgomot σ=10 0,547 → 0,618, blur 1 px 0,661 → 0,686.

**Scenariile demo:**
- **Scenariul 1 (seed 22):** 46 → **25** de finding-uri, 12 reale din 14 plantate (înainte 13), 12 „de urmărit”. Hot cell-ul critic e acum F-012 / AL-012 / WO-012 (B1-R5-T1-M11, ΔT 31,0 K). F-010 e un module_offline real, sigur.
- **`explain`:** cu ansamblul, seed-ul 23 nu mai avea nicio diodă sigură. Am scanat seed-urile 1–60 și am trecut pe **seed 19**: 18 finding-uri, 12 reale, o diodă sigură și reală (F-010), 11 cazuri nesigure cu ordin „verifică și repară”.
- Testele care fixau ID-uri din scenarii (F-022 → F-012, F-033 → F-010) și pragul T > 1 sunt adaptate. Testul Grad-CAM cere acum aceeași clasă ca ansamblul, nu logits egale.
- Analiza unei misiuni durează tot ~9 s.

**Verificare:**
- `cd backend && uv run pytest -q` → 236 passed;
- `uv run ruff check .` → curat;
- `cd ml && uv run pytest -q` → 20 passed (teste noi: `test_ensemble.py`);
- `cd frontend && npm run build` → verde;
- `npx playwright test` → 7 passed.
