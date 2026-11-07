# Opțional: test de degradare pe model

Type: task
Status: resolved
Owner: Tu
Țintă: după H20
Blocked by: 24

## Question

Spec: §3.6. Zgomot, blur și contrast, pe 3 niveluri, cu macro-F1 per nivel, în `evaluate.py`.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Code freeze H20: verificare cap-coadă](24-code-freeze.md)

## Answer

**Ce s-a construit:** în `evaluate.py`, `perturb(crops, kind, value, rng)` (numpy + PIL) și `degradation(classify, crops, y)`. Modelul din producție (`backend/artifacts/model.onnx`, prin `infer.probs`, cu T) rulează pe cele 2.977 de crop-uri de test perturbate, iar macro-F1 pe 8 clase se calculează pe fiecare nivel. Crop-ul perturbat e rotunjit înapoi la nivele de 8 biți și tăiat la 0–255, ca un crop real. Seed-ul e fix (`default_rng(0)`).

Nivelurile sunt în `DEGRADATIONS` din `evaluate.py`; nivelul 0 = crop-ul curat:

| perturbare | parametru | nivel 1 | nivel 2 | nivel 3 |
|---|---|---|---|---|
| zgomot gaussian | σ, în nivele de gri din 255 | 5 | 10 | 20 |
| blur (PIL `GaussianBlur`) | rază în px | 0,5 | 1 | 2 |
| contrast redus | fracțiunea de contrast păstrată față de media crop-ului | 0,75 | 0,5 | 0,25 |

**Rezultat (test, macro-F1, ResNet18 v1.1; curat 0,706):**

| | nivel 1 | nivel 2 | nivel 3 |
|---|---|---|---|
| zgomot | 0,701 | 0,547 | 0,264 |
| blur | 0,699 | 0,661 | 0,442 |
| contrast | 0,687 | 0,534 | 0,249 |

Modelul rezistă la perturbări mici: la nivelul 1 pierde cel mult 0,02. La nivelul 3 scade mult. Cu zgomot σ 20 sau contrast 25%, macro-F1 coboară sub cel al regulilor (0,374). Blur-ul îl afectează cel mai puțin.

**Schemă:** în `backend/app/schemas/eval.py` sunt noi `DegradationLevel` (`level`, `value`, `macro_f1`), `Degradation` (`kind`, `param`, `levels`) și câmpul `EvalReport.degradation`. DESIGN_SPEC §3.6 cere doar „macro-F1 per nivel” și nu numește câmpul, așa că am adăugat minimul necesar. `types.gen.ts` e regenerat din OpenAPI cu `openapi-typescript@7.13.0`.

**UI:** tab-ul Evaluare are secțiunea „Test de degradare” (`data-testid="degradation"`). Are un grafic Recharts cu linii (curat → nivel 3, câte o linie pe perturbare) și un tabel cu macro-F1 și valoarea parametrului pe fiecare nivel. Am corectat și NOTES din `evaluate.py`: robustețea pe pipeline e acum în `backend/tests/test_robustness.py` (tichetul 22).

**Cum am verificat:**
- `PYTHONUTF8=1 uv run --project backend python evaluate.py` → exit 0, cu cifrele de mai sus; `reports/eval.json` e regenerat. Cifrele existente nu s-au schimbat: reguli 0,374 · RF 0,541 · ResNet18 0,706, ECE 0,048 → 0,015, acoperire 60,1% la 96,0%. Rularea durează ~4,5 min, pentru că ResNet-ul cu TTA mai rulează de 9 ori.
- `cd backend && uv run pytest -q` → 217 passed. Testele noi sunt în `tests/test_evaluate.py`:
  - formă, interval 0–255 și valori întregi, pentru fiecare perturbare;
  - puterea perturbării: zgomotul crește deviația, blur-ul o scade, contrastul păstrează media și scalează deviația;
  - `degradation` cu un clasificator fals: nivelurile 0–3 și scorul pe curat.
- `tests/test_contracts.py` verifică acum că `eval.json` are cele 3 perturbări, fiecare cu 4 niveluri.
- `uv run ruff check .` (backend) și `ruff check evaluate.py` sunt curate.
- `cd frontend && npm run build` e verde. `npx playwright test` → 7 passed; `finding.spec.ts` verifică acum secțiunea de degradare (Zgomot/Blur/Contrast și graficul svg vizibil).
