# Modelul în pipeline: /api/analyse, inferență, incertitudine

Type: task
Status: resolved
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

## Answer

**Ce s-a făcut**
- `backend/app/services/pipeline/infer.py`: `load_model()` (onnxruntime, CPU) și `probs(model, crops, T)`: crop-uri `(n, 40, 24)` cu pixeli 0–255 → `/255` → ONNX → `softmax(z/T)`, în ordinea claselor din `model_meta.json`. Merge pe batch.
- `backend/app/services/pipeline/calibrate.py`: `load_temperature()`, `load_thresholds()`, `unsure_reason(p, th)` și `predictions(probs, T, th) → list[Prediction]`. Reguli: (1) `ok` cu ≥ `ok_max_risk` pe o clasă de risc → coadă; (2) încredere sub `min_conf[risk|other]` → coadă. Valorile implicite stau doar în `DEFAULT_TEMPERATURE` / `DEFAULT_THRESHOLDS`.
- `app/main.py`: modelul, T și pragurile se încarcă o dată în `lifespan`, în `app.state`.
- `POST /api/analyse`: acceptă PNG/JPG 24×40, răspunde cu `Prediction` de la model; 422 dacă nu e imagine sau nu e 24×40. Fără câmpuri noi în scheme, OpenAPI neschimbat.
- Dependență nouă: `onnxruntime` 1.31.1 (în lista permisă din `AGENTS.md`).

**Cum am verificat**
- `cd backend && uv run pytest -q` → `82 passed`. Testele noi sunt în `tests/test_model.py` (infer pe batch, efectul lui T, model pe fixture-uri, pragurile pe grup, `ok` cu masă de risc, fișiere care suprascriu valorile implicite, endpoint-ul cu 200 / 422). `test_contracts.py` trimite acum un crop real.
- `uv run ruff check .` → curat. `cd frontend && npm run build` → verde.
- Server real: `uv run uvicorn app.main:app --port 8010`, apoi `curl -X POST localhost:8010/api/analyse -F "file=@data/raptor/InfraredSolarModules/images/<id>.jpg"` pe crop-uri din `ml/splits/test.csv`:
  - `2.jpg` (adevăr module_offline) → `module_offline` 0,9995, unsure=false
  - `831.jpg` (diode_substring) → `diode_substring` 0,9992
  - `4851.jpg` (hot_cell) → `hot_cell` 0,9556
  - `10019.jpg` (ok) → `ok` 0,917
  - `2501.jpg` (shadow_vegetation) → `shadow_vegetation` 0,466, **unsure=true**, „încredere 0.47 sub pragul 0.60 (other)”
- Pe tot test split-ul (2.977 crop-uri, T=1, pragurile implicite): 423 merg în coadă, acuratețea pe ce trece automat e 0,821 (0,767 pe tot). **Ținta de 95% din §3.4 nu e atinsă cu valorile implicite**; pragurile reale vin din tichetul 09.

**Ce lipsește**
- Pipeline-ul misiunii nu există încă (tichetul 17, check/register/consistency, și simulatorul 16), iar misiunile servesc încă `mock_data`. Nimic din cod nu folosea baseline-ul pentru misiuni, deci n-a fost ce înlocui. Pipeline-ul 17 clasifică așa, în locul baseline-ului:
  ```python
  s = request.app.state  # sau app.state
  preds = calibrate.predictions(infer.probs(s.model, crops, s.temperature), s.temperature, s.thresholds)
  ```
  Baseline-ul rămâne doar pentru `Finding.baseline_cls` (§5).

## Comments

- **Format presupus pentru tichetul 09** (dacă fișierele lipsesc, se folosesc valorile implicite din `calibrate.py`):
  - `backend/artifacts/temperature.json`: `{"temperature": 1.42}`
  - `backend/artifacts/thresholds.json`:
    ```json
    {
      "risk_classes": ["hot_cell", "multi_hot", "diode_substring"],
      "min_conf": {"risk": 0.7, "other": 0.6},
      "ok_max_risk": 0.15
    }
    ```
  `min_conf` = probabilitatea maximă minimă ca predicția să treacă automat, pe grup de severitate. `ok_max_risk` = un `ok` cu cel puțin atât pe una dintre clasele de risc merge în coadă.
- Am scos o regulă de marjă (top-1 − top-2 < 0,15): cu probabilități normalizate și `min_conf ≥ 0,6` nu se poate declanșa niciodată.
- Fișierul `ruff format` semnalează `services/baseline/rules_classifier.py` (din 07), neatins aici.

- După merge cu 09: `calibrate.py` citește acum formatul scris de `ml/calibrate.py` (`min_conf` pe clasă, `max_risk_prob_ok` pe suma claselor de risc), aceeași regulă ca `unsure_mask`. Verificat: `uv run pytest -q` → 98 passed (test nou `test_reads_thresholds_written_by_ml_calibrate`), `/api/analyse` pe 3 crop-uri: diode_substring trece automat, hot_cell și module_offline (p=0,95) merg la `unsure` (prag 1,01 = mereu la inginer).