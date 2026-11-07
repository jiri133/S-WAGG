# evaluate.py, reports/eval.json și figuri

Type: task
Status: resolved
Owner: Tu
Țintă: H17
Blocked by: 07, 09

## Question

Spec: §3.6 (fără testul de degradare, care e tichetul 31). Rulează pe test o singură dată: reguli → RF → ResNet18, macro-F1 pe 8 și 12, F1 per clasă, matricea de confuzie, ECE, risk–coverage, analiza erorilor, cifrele de robustețe. `GET /api/eval` servește JSON-ul.

**Gata când:** `uv run --project backend python evaluate.py` regenerează totul de la zero.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Baseline: trăsături, reguli extinse la 8 clase, Random Forest](07-baseline.md)
- [Calibrare (temperature scaling) și praguri pe severitate](09-calibrare.md)

## Answer

`uv run --project backend python evaluate.py` (~30 s pe CPU) regenerează tot de la zero, pe `ml/splits/test.csv` (2.977 de crop-uri), o singură rulare:

1. în env-ul `ml/`: `data.download()` + `data.extract()` (idempotent, cu SHA-256), apoi `ml/baseline_rf.py --test` antrenează RF-ul determinist pe train (seed 42) și scrie predicțiile pe test în `backend/cache/rf_test_pred.json` (gitignored). sklearn rămâne doar în `ml/`;
2. în backend: reguli (`services/baseline/` + `config/baseline_rules.json`), ResNet18 ONNX prin `services/pipeline/infer.py`, T și pragurile prin `calibrate.py`;
3. metricile sunt în `backend/app/services/metrics.py` (numpy), raportul în `reports/eval.json`, validat de `EvalReport` (`backend/app/schemas/eval.py`).

**Cifre pe test:**

| model | macro-F1 (8) | macro-recall (12) |
|---|---|---|
| reguli | 0,374 | 0,331 |
| Random Forest | 0,541 | 0,451 |
| ResNet18 v1 | **0,657** | 0,709 |

- **Calibrare:** T = 1,68, ECE (15 bin-uri) **0,101 → 0,013**; reliability bins înainte/după în JSON.
- **Praguri (`thresholds.json`, alese pe val):** pe test trec automat **48,8%** din crop-uri, cu precizie **97,1%** (ținta ≥ 95%). Pe clasă: ok 1.128 la 97,2%, diode 236 la 97,0%, shadow 58 la 96,6%, other 32 la 96,9%; hot_cell, multi_hot, module_offline, soiling: 0 (mereu la inginer).
- **F1 ResNet18 pe clasă:** ok 0,88 · hot_cell 0,66 · multi_hot 0,45 · diode 0,95 · offline 0,49 · soiling 0,44 · shadow 0,70 · other 0,67.
- **Top confuzii (ResNet18), cu 6 exemple fiecare** (cele mai sigure greșeli, crop-ul ca PNG base64 în JSON): ok → module_offline 166, multi_hot → hot_cell 53, ok → shadow_vegetation 47, shadow_vegetation → hot_cell 42, hot_cell → multi_hot 38.
- Curba risk–coverage: 50 de puncte pe încrederea calibrată (risc 3,0% la 20% acoperire, 10,1% la 61%).

**Abateri și note, de confirmat:**
- **Schema:** §9 nu avea o schemă pentru `/eval`; ruta întorcea `dict[str, Any]`. Am adăugat `EvalReport` (minim, doar câmpurile de mai sus), ruta o folosește ca `response_model`, iar tipurile TS sunt regenerate (`EvalReport` în `api.ts`). `gen:types` țintește `:8000`; portul era ocupat, așa că am rulat aceeași comandă `openapi-typescript` pe `:8001`.
- **12 clase:** modelele prezic 8 clase, deci macro-F1 pe 12 nu e definit. Raportez recall-ul pe fiecare clasă Raptor (cât ajunge în clasa ei mapată) și media lui.
- **Robustețea (§6) lipsește:** simulatorul și check/register/consistency (16, 17, 22) nu există încă. Cifrele intră în `eval.json` odată cu tichetul 22. Degradarea e tichetul 31. Ambele sunt scrise în `notes` din JSON.
- **Figuri:** nu am adăugat matplotlib și nici PNG-uri; EvalView (tichetul 21) desenează din JSON cu Recharts.
- `reports/eval.json` are 40 KB din cauza celor 30 de crop-uri base64. E artefact generat (excepție de la regula de 30 KB), iar `test_file_size.py` nu verifică `.json`.

**Verificare:**
- `uv run --project backend python evaluate.py` rulat de două ori: aceleași cifre (determinist).
- `GET /api/eval` pe serverul pornit (`fastapi dev`, :8001) → 200, 34 KB, macro-F1 0,374 / 0,541 / 0,657, ECE 0,013, acoperire 0,488 la 0,971.
- `cd backend && uv run pytest -q` → **111 passed**. `test_evaluate.py` (9 teste, date sintetice): confuzie, F1 de mână, ECE = 0 la calibrare perfectă, bin-uri, risk–coverage, top confuzii, `model_scores` (recall 12), `selective` (regula unsure), `errors` (exemplele cele mai sigure + PNG). `test_contracts.py` validează `/api/eval` pe `EvalReport` (404 fără fișier).
- `uv run --project ml pytest -q ml/tests` → 6 passed. `ruff check` curat (backend + `evaluate.py` + `ml/baseline_rf.py`). `cd frontend && npm run build` → verde.

