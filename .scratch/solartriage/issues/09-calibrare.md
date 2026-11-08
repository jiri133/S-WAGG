# Calibrare (temperature scaling) și praguri pe severitate

Type: task
Status: resolved
Owner: Tu
Țintă: H13
Blocked by: 08

## Question

Spec: §3.4. `ml/calibrate.py` → `backend/artifacts/temperature.json` și `thresholds.json` (precizie ≥ 95% pe ce trece automat, praguri pe grup de severitate). ECE și reliability diagram înainte/după.

**Gata când:** fișierele există și ECE scade.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [ResNet18 pe Kaggle → model.onnx](08-resnet-onnx.md)

## Answer

`ml/calibrate.py` rulează `backend/artifacts/model.onnx` (v1) pe `ml/splits/val.csv` (2.995 de crop-uri, încărcate cu `train.load_split`), potrivește T prin NLL și scrie:

- `backend/artifacts/temperature.json`: **T = 1,680**; NLL 0,778 → 0,673; **ECE (15 bin-uri) 0,105 → 0,023**.
- `backend/artifacts/thresholds.json`: regula „unsure” plus cifrele pe val.
- `reports/reliability_val.png`: reliability diagram înainte/după (pillow). Înainte, barele de acuratețe stau sub diagonală (model prea sigur pe el); după, se aliniază.

**Regula** (backend-ul, adică tichetul 10, o aplică la fel): `p = softmax(logits/T)`, `c = argmax p`. Cazul e `unsure` dacă `p[c] < min_conf[c]` sau dacă `c == ok` și `Σ p[risk_classes] > max_risk_prob_ok` (0,15).

**Praguri:** ținta de precizie e pe grupul de severitate: risc (`hot_cell`, `multi_hot`, `diode_substring`) 98%, defect (`module_offline`, `soiling`, `shadow_vegetation`, `other`) 95%, `ok` 95%. Pragul se alege pe clasă, ca cel mai mic `min_conf` la care predicțiile trecute automat ating ținta grupului, pe minimum 20 de exemple. Altfel `min_conf = 1,01`, adică clasa merge mereu în coadă.

**Abatere față de spec, de confirmat:** spec-ul cere praguri pe grup de severitate. Cu un singur prag pe grup, `module_offline` (precizie ~31%) ar fi blocat și clasele bune din grupul lui, iar `multi_hot` ar fi blocat `diode_substring`. Am păstrat grupul ca nivel al țintei și am ales pragul pe clasă. `max_risk_prob_ok` rămâne fix la 0,15 (valoarea de start din spec): optimizat după acoperire, se relaxa singur la 0,49.

| clasă | min_conf | trec automat pe val | precizie |
|---|---|---|---|
| ok | 0,30 (+ risc ≤ 0,15) | 1.086 | 95,6% |
| diode_substring | 0,83 | 228 | 98,2% |
| shadow_vegetation | 0,96 | 65 | 96,9% |
| other | 0,98 | 23 | 95,7% |
| hot_cell, multi_hot, module_offline, soiling | 1,01 (mereu unsure) | 0 | n/a |

Acoperire 46,8%, precizie pe ce trece automat **96,1%**. Confuzia ok → module_offline: 202 cazuri pe val, **0 trec automat**. `hot_cell` și `multi_hot` nu ating 98% la niciun prag (maximum ~94% și ~90%), deci la v1 merg toate la inginer. Un model mai bun le-ar debloca.

Pragurile sunt alese și măsurate pe același val. Cifra cinstită vine din `evaluate.py`, pe test.

**Verificare:**
- `uv run --project ml python ml/calibrate.py` rulează cap-coadă în ~25 s pe CPU, cu cifrele de mai sus. Datele brute au fost copiate din worktree-ul 08 în `data/` (gitignored).
- `uv run --project ml pytest -q ml/tests`: 6 passed. Cele 4 teste noi din `ml/tests/test_calibrate.py` lucrează pe date sintetice: T > 1 pe logits supra-încrezători, NLL și ECE scad, ECE = 0 la calibrare perfectă, iar o clasă slabă e trimisă la `unsure` și cea bună nu (inclusiv regula ok-cu-risc). Testul scrie și PNG-ul.
- `uvx ruff check`: curat. `ml/calibrate.py` are 8,4 KB.
