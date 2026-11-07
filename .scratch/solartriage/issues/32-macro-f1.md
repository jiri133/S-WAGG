# Macro-F1 mai mare fără reantrenare: TTA cu flip-uri + bias pe clase

Type: task
Status: resolved
Owner: Tu
Țintă: H18
Blocked by: 08, 09, 15

## Question

Creștem macro-F1 al ResNet18 v1 (test 0,657) fără reantrenare pe Kaggle, cu două tehnici puse direct în graful ONNX, ca backend-ul să rămână neschimbat (intrare `crop` `(batch,1,40,24)` = pixel/255 → `logits` pe 8 clase):

1. **TTA cu flip-uri:** media pe 4 variante ale crop-ului (original, flip orizontal, flip vertical, ambele).
2. **Bias pe clase:** un vector de 8 valori adunat la logits, ales prin coordinate ascent pe o grilă ca să maximizeze macro-F1.

**Toate alegerile se fac doar pe val** (TTA da/nu, media pe logits sau pe probabilități, vectorul de bias). Bias-ul se alege înainte de temperatură; apoi `ml/calibrate.py` refit-uiește T și pragurile pe noul `model.onnx`. **Testul se folosește o singură dată, la final**, prin `evaluate.py`. Varianta nouă se păstrează doar dacă bate v1 pe val; altfel artefactele rămân neschimbate. `best.pt` (Grad-CAM) nu se schimbă.

**Gata când:** tabel cu macro-F1 pe val pentru cele 4 variante (v1, doar TTA, doar bias, ambele), cifrele noi pe test (macro-F1, F1 pe clase, ECE, acoperire la precizia țintă) față de cele vechi (0,657, ECE 0,013, 48,8% la 97,1%), comenzile rulate; teste în `ml/tests/`; backend, ruff, frontend și ml trec; `/api/analyse` răspunde valid.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`. Nu se atinge `backend/app/`.

### Depinde de

- [ResNet18 pe Kaggle → model.onnx](08-resnet-onnx.md)
- [Calibrare (temperature scaling) și praguri pe severitate](09-calibrare.md)
- [evaluate.py, reports/eval.json și figuri](15-evaluate.md)

## Answer

**Rezultat:** macro-F1 pe test **0,657 → 0,706** fără reantrenare. Varianta păstrată: TTA pe 4 flip-uri cu media pe **probabilități** + bias pe clase, ambele în `backend/artifacts/model.onnx`. Intrarea și ieșirea grafului sunt neschimbate (`crop ['batch',1,40,24]` → `logits ['batch',8]`), backend-ul nu e atins. `best.pt` (Grad-CAM) e neschimbat.

**Disciplina val/test:** toate alegerile s-au făcut doar pe `ml/splits/val.csv` (2.995 de crop-uri): TTA da/nu, media pe logits sau pe probabilități, grila de bias (±3, vezi mai jos) și vectorul de bias. Bias-ul s-a ales **înainte** de temperatură; T și pragurile s-au refăcut apoi cu `ml/calibrate.py` pe noul ONNX. Testul a fost folosit **o singură dată**, la final, prin `evaluate.py`; nicio alegere nu s-a făcut pe test.

### Val: macro-F1 pe cele 4 variante (`reports/boost_val.json`)

| variantă | val macro-F1 |
|---|---|
| v1 (ResNet18 fine-tuned, fără nimic) | 0,642 |
| doar TTA (media pe probabilități; pe logits: 0,662) | 0,661 |
| doar bias | 0,697 |
| **TTA + bias** (păstrată) | **0,719** (pe logits: 0,718) |

- Bias-ul ales (adunat la log din media softmax, `ok` fixat la 0): hot_cell −0,6 · multi_hot −0,3 · diode −2,3 · module_offline −2,9 · soiling +0,3 · shadow −0,3 · other +0,1. E salvat și în `model_meta.json` (`tta`, `class_bias`, `val_macro_f1_base`).
- **Ca să verific că nu e supraînvățat pe val:** bias ales pe jumătate din val (rândurile pare) și măsurat pe cealaltă jumătate, apoi invers. Fără bias 0,669 / 0,653, cu bias **0,719 / 0,703**, deci câștigul se păstrează pe date nevăzute la căutare.
- **Grila ±3** e aleasă tot pe val, din același test pe jumătăți. Cu ±2, module_offline stătea la marginea grilei; pe jumătatea nevăzută, ±2 dă 0,694, ±3 dă 0,711, iar ±4 dă 0,707.

### Test, o singură rulare (`reports/eval.json`), v1 → nou

| | v1 | nou |
|---|---|---|
| macro-F1 | 0,657 | **0,706** |
| acuratețe | 0,767 | 0,825 |
| ECE după T (15 bin-uri) | 0,013 (T 1,68) | 0,015 (T 1,36) |
| ECE înainte de T | 0,101 | 0,048 |
| trec automat (acoperire) | 48,8% la 97,1% precizie | **60,9% la 95,9%** (ținta minimă 95%) |

F1 pe clasă: ok 0,88 → 0,94 · hot_cell 0,66 → 0,70 · multi_hot 0,45 → 0,49 · diode 0,95 → 0,97 · **module_offline 0,49 → 0,71** · soiling 0,44 → 0,44 · shadow 0,70 → 0,72 · other 0,67 → 0,68.

Top confuzii: ok → module_offline (166 în v1) **a dispărut** din top 5. Acum: multi_hot → hot_cell 43, ok → shadow 39, hot_cell → shadow 38, multi_hot → other 34, shadow → hot_cell 33.

Trec automat pe clasă (test): ok 1.346 la 95,8% (era 1.128 la 97,2%) · multi_hot **23 la 87,0%** (era 0) · diode 244 la 98,0% · module_offline 37 la 94,6% (era 0) · shadow 129 la 95,3% · other 34 la 94,1%; hot_cell și soiling rămân 0 (merg mereu la inginer).

### De decis de om (nu am schimbat regulile de calibrare)

1. **multi_hot trece acum automat**, cu precizie 87,0% pe test față de ținta de 98% a grupului de risc. Pe val trecea cu 26 de exemple la 100%, abia peste `MIN_SUPPORT = 20`, deci pragul e ales pe prea puține exemple. Nu am corectat nimic după ce am văzut testul, ca să nu aleg pe test. Opțiuni: `MIN_SUPPORT` mai mare pentru grupul de risc, sau risc mereu la inginer.
2. **„ok” e mai permisiv:** pragul `min_conf[ok]` a coborât la 0,30 (ținta e 95%). Pe val, defectele care trec automat ca „ok” cresc de la 48 la 66, din 1.086 → 1.346 de „ok” automate; clasele de risc rămân aproape la fel (12 → 13), module_offline 8 → 15, shadow 28 → 37. Regula `max_risk_prob_ok = 0,15` rămâne activă.
3. **Grad-CAM** explică în continuare logits-urile lui `best.pt` pe crop-ul original, fără TTA și bias. Clasa explicată vine din pipeline, deci harta e pentru clasa corectă, dar nu e exact scorul modelului servit.

### Fișiere

- `ml/boost.py` (nou): `macro_f1`, `search_bias` (coordinate ascent pe grilă, numpy), `tta`, `view_logits`, `variants`, `half_check`; `--export` scrie ONNX-ul doar dacă bate v1 pe val și verifică ONNX față de numpy.
- `ml/export_onnx.py`: `Boosted` (Net + 4 flip-uri + bias, în graf), `load_net`, `export(..., tta, bias, val_macro_f1)`. Fără argumente se comportă ca înainte.
- `ml/tests/test_boost.py` (nou, 4 teste, date sintetice): macro-F1 = sklearn; bias-ul repară o clasă sub-prezisă; TTA pe logits/probabilități; ONNX exportat = numpy la 1e-4, invariant la flip, intrare `['batch',1,40,24]`, meta corect.
- `backend/tests/test_gradcam.py`: `test_torch_weights_match_onnx` aplică același TTA + bias din `model_meta.json` peste logits-urile `best.pt` (aceleași greutăți). `backend/app/` nu e atins.
- Artefacte regenerate: `model.onnx`, `model_meta.json`, `temperature.json` (T 1,359; ECE pe val 0,043 → 0,027), `thresholds.json` (pe val 60,4% la 95,6%), `reports/eval.json`, `reports/reliability_val.png`, `reports/boost_val.json`.

### Verificare (comenzi rulate)

- `uv run --project ml python ml/boost.py` → tabelul de mai sus; v1 reproduce exact 0,6422 din `model_meta.json`.
- `uv run --project ml python ml/boost.py --export` → `model.onnx` 44,7 MB; onnxruntime: intrare `crop ['batch', 1, 40, 24]`, ieșire `['batch', 8]`; pe val macro-F1 0,7194, max |ONNX − numpy| 4,2e-5.
- `uv run --project ml python ml/calibrate.py` → T 1,359, pragurile noi.
- `uv run --project backend python evaluate.py` (o singură dată) → reguli 0,374 · RF 0,541 · ResNet18 **0,706**; ECE 0,048 → 0,015; acoperire 0,609 la 0,959.
- `cd backend && uv run pytest -q` → **147 passed** (inclusiv `test_file_size.py`).
- `cd ml && uv run pytest -q` → **10 passed**.
- `uv run --project backend ruff check backend evaluate.py ml/*.py ml/tests` → curat. (`ruff check` pe tot `ml/` raportează 3 erori de import deja existente în `ml/notebooks/train_kaggle.ipynb`, neatins aici.)
- `cd frontend && npm ci && npm run build` → verde.
- `/api/analyse` pe serverul pornit (`fastapi dev`, :8132) cu crop-uri din `backend/tests/fixtures/crops/` → HTTP 200, T 1,359: `module_offline_17` → module_offline 0,86 (unsure, sub 0,94); `ok_10000` → ok 0,98 (auto); `multi_hot_3563` → multi_hot 0,995 (auto).

