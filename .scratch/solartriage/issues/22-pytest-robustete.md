# pytest: cele 6 cazuri de robustețe și regula de 30 KB

Type: task
Status: resolved
Owner: Alina
Țintă: H18
Blocked by: 17

## Question

Spec: §6 și §11. `backend/tests/test_robustness.py` (cele 6 cazuri), `test_contracts.py`, `test_file_size.py` (niciun fișier sursă peste 30.720 bytes, cu excepțiile din §11).

**Gata când:** `uv run pytest -q` trece pe ambele laptopuri.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Pipeline: data check, înregistrare GPS, consistency check](17-pipeline-check.md)

## Answer

Ramura `feat/22-pytest-robustete`, pornită din `docs/design-spec` @ `9e57c5f` (worktree-ul pornise din `origin/main` @ `1b61c9c`, fără tichetul 17; am creat ramura direct pe HEAD-ul `docs/design-spec`, care are 13, 15, 16 și 17). Nu am modificat `main`, nu am dat push.

**Ce am făcut**

- `backend/tests/test_robustness.py` (nou, ~8 KB, 6 teste) — fiecare caz din §6 rulează pipeline-ul real: `compose.frames` → `check.frame` → `register` → `infer` → `calibrate` → `consistency.merge`, pe cadre regenerate din `MissionSettings`. Refolosește `checked`, `_table_predictions`, `_outcomes` și `_glare_truth` din `tests/test_pipeline.py`.
  1. **Cadru lipsă** (`p_lost=0.5`, seed 7 → 24 de mese cu o trecere pierdută, 7 cu ambele): o trecere pierdută → cealaltă e folosită ca atare, 12/12 module acoperite, `seen_in_both_passes=False`; ambele pierdute → masa e în `not_inspected_tables` cu motivul „niciun cadru livrat”, adică exact lista de re-zbor; 0/12 module acoperite.
  2. **Iradianță < 600** (`inject=["low_irr"]`): ambele cadre respinse cu motivul „iradianță … < 600”; masa intră în `not_inspected`, iar `_table_predictions` întoarce `{}` — cadrele respinse nu ajung la model, deci 0 finding-uri. Cu `p_cloud=1`, toate cele 80 de cadre sunt respinse, toate cele 40 de mese sunt `not_inspected` și nicio masă nu produce predicții.
  3. **RGB** (`inject=["rgb"]`): ambele cadre respinse cu „nu e radiometric: 3 canale” și „imaginea are 3 canale”; masa `not_inspected`, fără inferență.
  4. **Fără panouri** (`inject=["no_panels"]`): ambele cadre respinse cu „nicio grilă de module”; masa `not_inspected`, fără inferență.
  5. **Glare** (`p_glare=1`, `n_faults=0`): pentru fiecare masă, predicțiile reale pe cele două treceri trec prin `consistency.merge`. Orice anomalie văzută într-o singură trecere iese `reflection`, `unsure`, `urgency="low"`, cu motivul „reflexie probabilă”; modulele atinse sunt exact cele sub petecul de glare din simulator și nu apar niciodată ca finding. Înainte/după: `before` (toate modulele cu anomalie) = `queue ∪ findings`, iar `queue ∩ findings = ∅` — consistency check-ul sortează toate anomaliile și nu inventează niciuna. Pe crop-uri sintetice, testul a găsit 45 de reflexii în coadă și 0 finding-uri confirmed.
  6. **Decalaj GPS** (`p_gps=1`): offset-ul e detectat pe toate cele 80 de cadre (egal cu adevărul din `artefacts.plan`, ±1) și corectat; sloturile realiniate sunt identice cu cele din zborul aliniat, iar pozițiile 1/7 (la +1) și 6/12 (la −1) nu au imagine. Predicțiile/outcomes pe cele ≥ 320 de module comune ambelor zboruri sunt identice (clasă, `unsure`, motiv, `reflection`, `urgency`, treceri, probabilități).
- `backend/tests/test_pipeline.py` — `_outcomes` memorează rezultatul pe `settings`, ca testul GPS din `test_robustness.py` să nu ruleze a doua oară aceleași două misiuni prin model (sunt exact zborurile din `test_gps_correction_gives_the_aligned_predictions`).
- `backend/tests/test_file_size.py` — §11 listează `.j2` printre fișierele sursă, dar `EXTS` nu îl verifica. L-am adăugat și am adăugat un test care pică pe un `report.html.j2` > 30 KB și ignoră un `types.gen.ts` mare (excepția din §11).
- `test_contracts.py` — revizuit: toate endpoint-urile din §9 implementate sunt deja acoperite (inclusiv `GET /missions/{id}/alerts` + `POST /alerts/{id}/ack`, csv-urile, PNG-urile, SSE, `/eval`); nu am găsit un gol, deci nu l-am modificat.
- Niciun bug de producție găsit; nu am schimbat `backend/app/`.

**De știut**

- „Propunerea de re-zbor” e, în pipeline-ul de față, exact setul din `not_inspected_tables` (masă + motiv). Evenimentul `refly_proposed` din jurnal (`AgentEvent`) se emite în tichetul 18, când se compune misiunea; `mock_data` are deja kind-ul.
- Testul de glare depinde de modelul real; pe crop-uri sintetice (fără `data/raptor`) glare-ul e prins în 45 de module. Dacă modelul nu ar vedea glare-ul deloc, `assert queue` ar pica — e intenționat, ca testul să nu treacă în gol.

**Cum am verificat**

- `cd backend && uv run pytest -q` → **175 passed, 1 skipped** (168 înainte + 6 robustețe + 1 file-size), 65.17 s. Skip-ul e `test_real_crops_come_from_the_test_split` (crop-urile Raptor nu sunt descărcate pe acest laptop; se folosesc cele sintetice).
- `cd backend && uv run ruff check .` → **All checks passed!**
- `cd frontend && npm ci --no-audit --no-fund && npm run build` → **built in 480ms**, 37 modules, `dist/assets/index-*.js` 267.70 kB (frontend-ul nu a fost atins de tichet).
