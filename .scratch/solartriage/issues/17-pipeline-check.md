# Pipeline: data check, înregistrare GPS, consistency check

Type: task
Status: resolved
Owner: Alina
Țintă: H8
Blocked by: 16

## Question

Spec: §5 pașii 1, 2 și 4. `services/pipeline/check.py`, `register.py`, `consistency.py`. Până la tichetul 10, clasificarea folosește baseline-ul.

**Gata când:** mesele cu probleme devin `not_inspected` cu motiv, decalajul GPS e corectat, iar glare-ul dintr-o singură trecere ajunge în coadă.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Simulator în FastAPI: parc, compunere Raptor, 2 treceri, artefacte](16-simulator.md)

## Answer

Ramura `feat/17-pipeline-check`, pornită din `docs/design-spec` @ `93ac59d`, cu `origin/main` (tichetul 16, merge-ul care a intrat din greșeală în `main`) adus prin merge. Codul e în `backend/app/services/pipeline/`.

**Ce face**

- `check.py` — pasul 1. `problems(meta, img)` respinge: iradianță < 600 W/m², vânt > 8 m/s, lipsă timp/poziție, temperaturi invalide (NaN sau în afara −40…150 °C), cadre RGB (`channels ≠ 1` sau `radiometric=false`) și cadre fără grilă de module (sol uniform la 28 °C). `frame()` întoarce `FrameMeta` cu `check_ok` și `problems`; `not_inspected_tables()` dă mesele fără niciun cadru valid și motivul fiecăreia (uniunea problemelor, sau „niciun cadru livrat”).
- `register.py` — pasul 2. `offset(img)` caută coloana de sol de la margine (plată și la 28 °C) și întoarce −1, 0 sau +1; `slots(img, gps)` re-alocă pozițiile 1–12 la crop-urile de 24×40. Pozițiile fără imagine (1 și 7 la +1; 6 și 12 la −1) lipsesc din rezultat.
- `consistency.py` — pasul 4. `merge({pass_no: {module_id: Prediction}})` întoarce câte un `Outcome`: anomalie în ambele treceri → finding; anomalie într-o singură trecere → „reflexie probabilă”, `Prediction.unsure=True` cu motiv și `urgency="low"` (coada de review); o trecere lipsă → se folosește cealaltă. Modulele fără nicio imagine nu apar (rămân `not_inspected`).
- `compose.to_gray()` — inversa conversiei din §4 (`pix = median_ok + (T − T_bază)/k`), ca sloturile în °C să ajungă la model.
- `GET /api/missions/{id}/frames` completează acum `check_ok`, `problems` și `gps_offset_detected` (pașii 1–2); până la tichetul 18, misiunea folosește `MissionSettings()`.

**Cum am verificat**

- `cd backend && uv run pytest -q` → **159 passed, 1 skipped** (131 înainte + 28 în `tests/test_pipeline.py`). `uv run ruff check .` → curat. `cd frontend && npm run build` → verde.
- Testele acoperă „Gata când”:
  - fiecare respingere din §5 (iradianță, vânt, timp/poziție, temperaturi, RGB, fără panouri) și mesele `not_inspected` cu motiv: nor pe ambele treceri, `low_irr`, `rgb`, `no_panels`, `missing` („niciun cadru livrat”); o singură trecere pierdută lasă masa inspectată;
  - offset-ul GPS e detectat pe toate cele 80 de cadre ale unui zbor cu `p_gps=1` și corectat: sloturile realiniate sunt identice cu cele din zborul aliniat, iar predicțiile modelului pe modulele comune sunt identice (≥ 320 de module); pozițiile 1/7 și 6/12 nu au imagine la ±1;
  - o anomalie doar într-o trecere ajunge în coadă: test determinist pe geometria glare-ului din simulator, plus cap-coadă cu modelul real.
- Server real pe :8011: `GET /api/missions/M-0001/frames` → 200 în 0,34 s, 78 de cadre, 9 respinse (iradianță 423–475 W/m²), `gps_offset_detected=+1` pe 3 cadre; thumbnail 200; `/api/park` 200.
- Cap-coadă cu modelul real (crop-uri sintetice, fără `data/`): pe un zbor cu `p_glare=1` și `n_faults=0`, 45 din 46 de module atinse de glare au ieșit „reflexie probabilă” în coadă, 0 reflexii în altă parte. Nu e test automat, fiindcă depinde de crop-urile și modelul folosite.

**De știut pentru tichetul 18**

- `/analyse` trebuie să compună: `compose.frames` → `check.frame` → `check.not_inspected_tables` → pentru fiecare masă validă și trecere `register.offset`/`register.slots` → `compose.to_gray` → `infer.probs` → `calibrate.predictions` → `consistency.merge`. `Outcome.urgency` se folosește când nu e `None` (adică `"low"` la reflexie); altfel decide stratul de decizie.
- `Outcome.passes` spune în ce treceri a fost văzut modulul; `seen_in_both_passes` intră direct în `Evidence`.
- Modulele absente din `merge` n-au imagine în nicio trecere și devin `not_inspected`; o trecere lipsă nu înseamnă neinspectat.
- `gps_offset_detected` se detectează doar pe cadrele care trec data check-ul; un cadru respins îl lasă 0.
- `FrameMeta` are acum câmpurile completate pe `/frames`; tipurile TypeScript nu se schimbă (schema e aceeași).
