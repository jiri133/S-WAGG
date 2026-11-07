# Opțional: CNN mic de ablație

Type: task
Status: resolved
Owner: Tu
Țintă: după H20
Blocked by: 24

## Question

Spec: §3.3 punctul 4. Un CNN antrenat de la zero, ca al patrulea rând în tabelul de evaluare.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Code freeze H20: verificare cap-coadă](24-code-freeze.md)

## Answer

**Ce s-a construit:** `ml/train_small.py` cu `SmallNet`, un CNN antrenat de la zero, fără pre-antrenare:
- 3 blocuri, fiecare cu 2 × (conv 3×3 + BatchNorm + ReLU) și un max-pool; canale 32 → 64 → 128, iar crop-ul trece de la 40×24 la 5×3;
- apoi global average pool, dropout 0,3 și un strat liniar pe 8 clase;
- ~290 k parametri, față de ~11 M la ResNet18; lucrează direct pe crop-ul 40×24, fără redimensionare.

Bucla de antrenare **nu e copiată**. `train.train(args, model=None)` primește acum modelul opțional; implicit rămâne ResNet18 `Net`, deci ResNet-ul se antrenează exact ca înainte. CNN-ul mic folosește aceeași buclă, deci și:
- același split train;
- aceleași augmentări (flip H/V, ±luminozitate, zgomot);
- aceeași echilibrare (oversampling + class weights ∝ 1/√n);
- aceeași selecție pe macro-F1 pe val.

Valorile implicite: 15 epoci, lr 3e-3 (OneCycle, AdamW), batch 128, seed 42.

**Export și evaluare:** modelul se exportă în `backend/artifacts/small_cnn.onnx` (1,15 MB), cu aceeași intrare și ieșire ca modelul din producție: `crop` `(batch,1,40,24)` = pixel/255 → `logits`. `evaluate.py` îl notează cu onnxruntime prin același `infer.probs` (T = 1, argmax) și îl pune al 4-lea rând în tabel, ca `small_cnn` (afișat „CNN mic (de la zero)”). `model.onnx`, `best.pt`, `model_meta.json`, temperatura și pragurile **nu sunt atinse**. Backend-ul nu servește `small_cnn.onnx`.

**Rezultat:**
- **Antrenare pe CPU:** 15 epoci × ~22 s ≈ 5,5 min. Cel mai bun model e la epoca 11, cu val macro-F1 **0,565**. Pe val, scorul oscilează mult între epoci (0,36–0,56).
- **Test, o rulare prin `evaluate.py`:** macro-F1 **0,588**, acuratețe 0,719, macro-recall pe 12 clase 0,598. Ordinea în tabel: reguli 0,374 · RF 0,541 · **CNN mic 0,588** · ResNet18 0,706.
- **F1 pe clasă:** ok 0,85 · hot_cell 0,58 · multi_hot 0,39 · diode 0,89 · module_offline 0,38 · soiling 0,31 · shadow 0,59 · other 0,71.
- **Concluzia ablației:** CNN-ul de la zero bate baseline-urile pe trăsături (+0,05 față de RF). ResNet18 mai câștigă +0,12 macro-F1, din pre-antrenarea ImageNet plus TTA/bias. Diferențele cele mai mari sunt pe module_offline și shadow.
- **De notat:** ResNet18 din tabel include TTA + bias pe clase (tichetul 32), iar CNN-ul mic nu. Comparația nu izolează strict efectul pre-antrenării.

**Cum am verificat:**
- `uv run --project ml python ml/train_small.py` → exit 0, cu log-ul pe epoci de mai sus; `small_cnn.onnx` e scris.
- `PYTHONUTF8=1 uv run --project backend python evaluate.py` → exit 0, `small_cnn macro-F1 0.588`. Celelalte cifre nu s-au schimbat: 0,374 / 0,541 / 0,706, ECE 0,048 → 0,015, degradarea identică.
- `cd ml && uv run pytest -q` → 14 passed. Testele noi sunt în `tests/test_train_small.py`:
  - forma ieșirii și sub 500 k parametri;
  - 5 pași AdamW pe un batch de 8 scad loss-ul;
  - exportul ONNX dă aceleași logits ca PyTorch (rtol 1e-3).
- `test_train_export.py`, care antrenează ResNet-ul prin `train.train`, trece în continuare.
- `cd backend && uv run pytest -q` → 217 passed; `test_contracts.py` cere acum modelele `rules, random_forest, resnet18, small_cnn`.
- Ruff e curat pe backend, `evaluate.py`, `ml/train.py`, `ml/train_small.py` și `ml/tests`. Erorile ruff din `ml/notebooks/train_kaggle.ipynb` existau dinainte; notebook-ul nu e atins.
- `cd frontend && npm run build` e verde. `npx playwright test` → 7 passed; `finding.spec.ts` verifică acum rândul „CNN mic (de la zero)” din tabelul de modele.
