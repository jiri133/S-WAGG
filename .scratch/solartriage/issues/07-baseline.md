# Baseline: trăsături, reguli extinse la 8 clase, Random Forest

Type: task
Status: resolved
Owner: Tu
Țintă: H7
Blocked by: 06

## Question

Spec: §3.3.

- `backend/app/services/baseline/features.py` și `rules_classifier.py`: `classify()` din PoC portat pe intensitate, extins la 8 clase, cu praguri ajustate pe train.
- RF în `ml/`, pe aceleași trăsături.

**Gata când:** există tabelul macro-F1 pe val pentru ambele baseline-uri.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Date ML: descărcare Raptor, dedup, split, mapare 12→8](06-date-ml.md)

## Answer

**Ce există acum:**
- `backend/app/services/baseline/features.py`: 17 trăsături numpy pe crop-ul gri 24×40 (0–255, nu °C): `median`, `std`, `peak` (max − mediană), `hot_frac` (> mediană + 20), `n_blobs` și `largest_blob` (pete fierbinți 4-conexe, ≥ 2 px), `n_warm_cells`/`n_hot_cells` (celule 4×4 peste mediană + 8 / + 20), `band_contrast`, `band_cover`, `band_spread` (cele 3 benzi verticale de 1/3 = substring-urile cu diodă bypass), `uniform_frac`, `cold_frac`, `bottom_delta`, `top_delta`, `row_spread`, `frame_contrast` (modulul față de inelul exterior de 1 px, pentru „modul uniform cald” = offline). Crop-ul are un cadru întunecat de 1–2 px, deci măsurăm pe interior; benzile sar peste rampa de 4 px de la margini.
- `backend/app/services/baseline/rules_classifier.py`: `classify()` din PoC, ca listă de decizie în ordine fixă pe toate 8 clasele: diode → offline → other → soiling → multi_hot → hot_cell → shadow_vegetation → altfel `ok`. Pragurile sunt în `backend/config/baseline_rules.json`. `classify(crop)` e funcția pe care o va apela pipeline-ul pentru `Finding.baseline_cls`.
- `ml/tune_rules.py`: coordinate descent pe **train** (fiecare prag încearcă 41 de cuantile ale trăsăturii sale, 4 treceri, maximizează macro-F1 pe train), scrie JSON-ul, apoi raportează pe val. Determinist: a doua rulare a produs același JSON byte cu byte.
- `ml/baseline_rf.py`: Random Forest (500 de arbori, `class_weight="balanced_subsample"`, `min_samples_leaf=2`, seed 42) pe aceleași 17 trăsături, antrenat pe train, scor pe val. `train_rf()` poate fi importat de `evaluate.py` pentru test.
- `backend/pyproject.toml`: am adăugat `numpy` și `pillow` (ambele pe lista permisă).
- Test nu e citit nicăieri aici, rămâne pentru `evaluate.py`.

**Tabel pe val (2995 de crop-uri), F1:**

| clasa | reguli | Random Forest |
|---|---:|---:|
| ok | 0,744 | 0,862 |
| hot_cell | 0,406 | 0,469 |
| multi_hot | 0,240 | 0,373 |
| diode_substring | 0,575 | 0,787 |
| module_offline | 0,190 | 0,465 |
| soiling | 0,200 | 0,211 |
| shadow_vegetation | 0,121 | 0,454 |
| other | 0,464 | 0,621 |
| **macro-F1** | **0,367** | **0,530** |

Pe train, regulile ajung la 0,357 macro-F1 (de la 0,321 cu pragurile puse de mână), deci nu sunt supra-ajustate. Două praguri au ajuns practic dezactivate de tuner (`offline_uniform` = 0,03 și `shadow_cold` = 0): acele condiții nu ajutau pe train. `soiling` rămâne slab la ambele (143 de crop-uri în train).

**Cum am verificat:**
- `uv run --project ml python ml/data.py`: split-urile sunt identice cu cele din repo (`git status` curat). Datele le-am copiat din worktree-ul tichetului 06, `data/` e în `.gitignore`.
- `uv run --project ml python ml/tune_rules.py`: ~75 s, rezultatul de mai sus; rulat de două ori, JSON identic.
- `uv run --project ml python ml/baseline_rf.py`: ~35 s, tabelul de mai sus.
- `cd backend && uv run pytest -q`: **49 passed** (cele vechi + `tests/test_baseline.py`: blob-uri, celulă fierbinte sintetică, bandă de substring, modul plat = `ok`, modul uniform mult mai cald decât cadrul = `module_offline`, pragurile acoperă toate regulile, plus câte un crop Raptor real per clasă în `tests/fixtures/crops/`).
- `ruff check` curat pe `backend/` și pe cele 2 scripturi din `ml/`.
- Fișierele sunt sub 5 KB fiecare. `npm run build` nu l-am rulat: tichetul nu atinge `frontend/`.

**De știut:** crop-urile reale din teste sunt primele din train pe care regulile le clasifică corect (câte unul per clasă), deci testul prinde regresii, nu măsoară acuratețea. Acuratețea e tabelul de mai sus.
