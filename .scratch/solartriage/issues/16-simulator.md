# Simulator în FastAPI: parc, compunere Raptor, 2 treceri, artefacte

Type: task
Status: resolved
Owner: Alina
Țintă: H6
Blocked by: 05

## Question

Spec: §4. `services/sim/park.py` (2×5×4 mese, ID-uri, string-uri, invertoare), `compose.py` (slot 24×40 din crop-uri Raptor din test, conversie în temperatură aparentă), `artefacts.py` (nor, glare pe o trecere, GPS cu sol, cadru pierdut, RGB, fără panouri, iradianță scăzută). Totul determinist din `seed`.

Până e gata tichetul 6: crop-uri sintetice de rezervă, generate ca în PoC.

**Gata când:** același seed dă aceleași cadre, iar toate injectările se pot activa din `MissionSettings`.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Scheme Pydantic, mock-uri FastAPI și schelet React cu tipuri generate](05-contracte.md)

## Answer

Ramura `feat/alina-16-simulator` (worktree `.claude/worktrees/16-simulator`), pornită din `docs/design-spec` @ `2542a79`. La cererea sesiunii principale, cu acordul Alinei, am adus apoi prin merge `docs/design-spec` @ `183daff`. Conflictele: `pyproject.toml` și `uv.lock` au rămas ca pe `docs/design-spec`, iar `mock_data.py` păstrează importurile din ambele părți. Fără push.

**Ce face** (`backend/app/services/sim/`)

- `park.py`: cele 480 de module din §4 (2 blocuri × 5 rânduri × 4 mese × 12). ID-urile au forma `B1-R2-T3-M07`. Un string (`B1-R2-S2`) leagă 2 mese, adică 24 de module, iar fiecare rând are un invertor (`INV-1.2`) cu 48 de module. Rândurile sunt la 9 m pe y, iar cele 2 blocuri stau alăturate, la 45 m pe x. În mock erau unul sub altul și distanța dintre blocuri nu se vedea. `x_m`/`y_m` e colțul stânga-sus al modulului. Codul s-a mutat din `mock_data.py`, care acum îl importă.
- `compose.py`: un cadru e o masă, adică 2×6 sloturi de 24×40 (144×80 px). Fiecare slot primește un crop din `ml/splits/test.csv` din clasa plantată a modulului (`ok` pentru modulele sănătoase), convertit cu `T = T_bază + (pix − median_ok) × 0,15`. Pe crop-urile reale, `median_ok` = 156. Cele `n_faults` module cu defect primesc o clasă aleasă uniform dintre cele 7.
  - `truth()` dă adevărul de teren pentru toate cele 480 de module.
  - `frames()` dă metadatele (`FrameMeta`); cadrele pierdute lipsesc.
  - `frame_image()` regenerează pixelii: °C float32, sau RGB uint8 pentru injectarea `rgb`.
  - `png()` face thumbnail-ul, în gri de la 10 la 70 °C.
- `artefacts.py`: `plan()` trage artefactele din seed.
  - Pe cadru: nor (`p_cloud`, 420–480 W/m²), decalaj GPS de ±1 modul (`p_gps`, slotul liber arată sol la 28 °C) și cadru pierdut (`p_lost`).
  - Pe masă: glare în exact una din cele 2 treceri (`p_glare`, 2×2 celule, +7…11 K).
  - Fiecare valoare din `inject` lovește ambele treceri ale unei mese alese din seed: `rgb` (3 canale, `radiometric=false`), `no_panels` (doar sol), `low_irr` (520–590 W/m²) și `missing` (niciun cadru).
  - `T_bază = 20 °C + 25 K × G / 800` (NOCT 45 °C), deci scade sub nor: ~46 °C la soare, ~34 °C la 450 W/m².
- **Determinism:** totul vine din `numpy.random.default_rng([seed, flux])`, cu fluxuri separate pentru defecte, crop-uri, artefacte și zgomotul solului, și cu trageri de mărime fixă. Schimbarea unei probabilități sau a unei injectări nu mută defectele, celelalte artefacte sau mesele celorlalte injectări. Crop-urile din cache sunt read-only.
- **Rute:** `GET /api/park`, `GET /api/missions/{id}/frames` și `GET /api/frames/{id}/thumb.png` servesc acum simulatorul. Un cadru necunoscut sau pierdut dă 404. Până la tichetul 18, toate misiunile zboară cu `MissionSettings()` implicit, ca mock-urile. Crop-urile se citesc o singură dată, în `lifespan`.
- **`MissionSettings`:** aceleași câmpuri și valori implicite, plus limite: `0 ≤ seed ≤ 2³¹−1`, `0 ≤ n_faults ≤ 480`, probabilități în [0, 1] și `speed` finit și > 0. O valoare greșită dă 422 în loc de crash.
- `numpy` și `pillow` vin din `docs/design-spec` (tichetele 07 și 08). Am regenerat `types.gen.ts`; s-au schimbat doar descrierile celor 2 rute de cadre.
- **Crop-urile reale:** se descarcă o dată pe checkout, cu `uv run --project ml python ml/data.py` (`data/` e în `.gitignore`). Fără ele (CI, Docker), simulatorul folosește crop-uri sintetice cu pattern-urile din §3.3 și scrie un warning în log.

**Cum am verificat**

- `cd backend && uv run pytest -q`: **101 passed**, adică cele 73 de pe `docs/design-spec` plus 28 din `tests/test_sim.py`. `uv run ruff check .`: All checks passed.
- Fără `data/`, ca în CI: 100 passed și 1 skipped (testul crop-urilor reale).
- `cd frontend && npm run build`: ok. `npm run lint`: exit 0.
- Testele acoperă „Gata când”:
  - același seed dă același hash pe toate cadrele, în proces și într-un alt proces cu alt `PYTHONHASHSEED`;
  - fiecare valoare din `inject` și fiecare probabilitate se activează din `MissionSettings`;
  - fiecare slot conține un crop din clasa plantată, convertit în temperatură aparentă;
  - defectul apare în ambele treceri, glare-ul doar într-una;
  - decalajul GPS mută masa și arată sol;
  - cele 2 treceri ale unei mese sunt la 1 m și 4 s una de alta.
- Backend pe :8001 (`fastapi dev --port 8001`), după merge și reparațiile din review:
  - `/api/park` dă 480 de module;
  - `/api/missions/M-0001/frames` dă 78 de cadre: 2 pierdute și 9 sub 600 W/m² din cauza norului;
  - thumbnail-urile pentru cadru normal, cu GPS, cu glare și cu nor dau 200 `image/png`; primul răspunde în 45 ms, pentru că crop-urile sunt deja încărcate la pornire;
  - cadrul pierdut și un id inexistent dau 404;
  - `POST /api/missions` cu `n_faults=999`, `seed=-1` sau `seed=2³¹` dă 422;
  - ordinele de lucru din tichetul 11 iau string-ul și invertorul din noul parc;
  - fără erori în log.
- Înainte de merge (codul simulatorului nu s-a schimbat de atunci):
  - SSE-ul trimite cadrul simulatorului, iar `flight_done` = 78.
  - Frontend-ul pornit pe :5174 cu proxy spre :8001 afișează „480 module · 2 blocuri · 10 invertoare”, fără erori în consolă.
  - Un contact sheet verificat vizual arată: sol în dreapta la GPS +1, pătratul de glare într-o singură trecere, cadre mai întunecate la nor și la `low_irr`, RGB albastru, doar sol la `no_panels`, niciun cadru la `missing` și defectele identice în ambele treceri.
- **Review `ecc:fastapi-reviewer`**, rulat cu Opus, pentru că modelul implicit al agentului (`deepseek-flash`) nu există în cont. N-a găsit nimic CRITICAL sau HIGH.
  - Reparate: testul că slotul conține un crop din clasa plantată (MEDIUM), `seed ≤ 2³¹−1`, `speed` finit și citirea crop-urilor în `lifespan`.
  - Lăsat, fallback-ul sintetic la un set de date parțial: ar ține crop-uri sintetice în cache tot procesul și ar ascunde o instalare stricată, pe când acum eroarea se vede.
  - Lăsate, listele imuabile pentru parc: nimic nu le modifică, iar `Module` rămâne mutabil și într-un tuplu.
  - Lăsat, 404 declarat în OpenAPI: nici celelalte rute nu-l declară.

**De decis de om** (nu am schimbat spec-ul)

1. **Cu k = 0,15 K/nivel, pragul de 20 K nu se atinge.** Am măsurat ΔT aparent (vârful modulului față de mediana mesei, ca în glosar) pe crop-urile reale, pe 60 de seed-uri. hot_cell: p50 7,2 K, p90 13,4 K, max 18,3 K. multi_hot: p90 15,0 K. diode_substring: p90 12,2 K. Niciun caz (0 %) nu ajunge la 20 K. Deci regula de siguranță din §7 nu se declanșează, iar scenariul demo 1 („hot cell cu ΔT 22 K”) nu se poate obține. Ca p90-ul claselor de risc să ajungă la ~20 K, k ar trebui să fie ~0,20–0,25. E exact întrebarea din „Not yet specified” din `map.md`.
2. **Crop-urile `ok` au luminozități foarte diferite:** mediana pe crop merge de la 88 (p5) la 205 (p95) nivele. De aceea modulele sănătoase din aceeași masă diferă cu până la ~17 K, iar ΔT al unui modul `ok` ajunge la 8,5 K (p90). Luminozitatea absolută poartă însă semnal (mediana e 187 la `module_offline` și 162 la `ok`), deci n-am normalizat crop-urile.
3. **PoC-ul** (`pv-inspection-poc`) nu e pe laptop și nici public pe GitHub. Crop-urile sintetice nu sunt copiate din el. Urmează pattern-urile din §3.3: punct fierbinte, mai multe pete, bandă pe 1/3, modul uniform cald, murdărie pe margine, umbră în colț, fisură.

**De știut pentru tichetele următoare**

- **17 (pipeline):**
  - În simulator, `check_ok`, `problems` și `gps_offset_detected` rămân neutre (True, [], 0); le completează pipeline-ul.
  - Modelul din tichetul 08 primește pixel/255, deci temperatura trebuie întoarsă în pixeli cu `pix = median_ok() + (T − T_ref) / K_PER_LEVEL`. Constantele sunt în `compose`.
  - `artefacts.plan(settings)` dă adevărul despre artefacte (GPS real, glare, nor, cadru pierdut), pentru teste și pentru `evaluate.py`.
  - Convenția GPS: +1 înseamnă că camera a privit cu un modul mai departe pe +x, deci ultima coloană de sloturi e sol.
  - `missing` scoate ambele treceri ale unei mese, care devine `not_inspected`. Cazul cu o singură trecere pierdută vine din `p_lost`; cu seed 7 implicit sunt `FR-B2-R3-T4-P2` și `FR-B2-R5-T3-P1`.
- **18 (stare):** rutele de cadre folosesc acum `MissionSettings()`. Ruta `/frames/{id}/thumb.png` nu are misiunea în cale, iar id-urile `FR-{masă}-P{trecere}` se repetă între misiuni și re-zboruri. Starea trebuie deci să mapeze id-ul la misiune; altfel browserul poate arăta din cache thumbnail-ul altei misiuni.
- **Mock-urile rămase nu se potrivesc cu cadrele reale.** `Mission.truth`, alerta AL-001 și jurnalul mock descriu B1-R2-T3-M07 și FR-B2-R4-T3-P1 altfel decât le arată cadrele simulatorului (seed 7). Se rezolvă când 17 și 18 înlocuiesc misiunea și finding-urile mock.
- **Cadrele sunt deterministe în același mediu.** Ies altfel în Docker (imaginea conține doar `backend/`, deci se folosesc crop-urile sintetice) sau cu alte versiuni de numpy/Pillow decât cele din `uv.lock`.
- La `inf`/`NaN` în JSON, pe orice câmp numeric (de exemplu `{"p_glare": 1e999}`), FastAPI întoarce 500 în loc de 422, pentru că handler-ul implicit de 422 nu poate serializa `inf`. Schema le respinge corect. Ca să iasă 422, e nevoie de un handler propriu pentru `RequestValidationError`.
- `ml/data.py` crapă pe Windows când ieșirea e redirecționată (print cu diacritice în cp1252), dar abia după ce a descărcat și extras datele. Merge cu `PYTHONUTF8=1`.
- `types.gen.ts` de pe `docs/design-spec` nu are încă descrierile a 2 rute din tichetul 11 (sunt doar comentarii). Trebuie regenerat acolo.
- `ruff format --check` pică pe `backend/app/services/baseline/rules_classifier.py` (tichetul 07). CI rulează doar `ruff check`, care trece.
