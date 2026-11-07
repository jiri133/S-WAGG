# Harta SolarTriage

Type: map

## Destination

SolarTriage construit și gata de demo la H24, conform `docs/DESIGN_SPEC.md`: agent cap-coadă în **FastAPI**, UI în **React (Vite)**, model antrenat și evaluat față de 2 baseline-uri, `evaluate.py` reproductibil, repo public cu commit-uri în cele 24 h.

## Notes

- **Execuția e inclusă în hartă** (excepție de la regula Wayfinder „plan, don't do”). Tichetele `task` sunt bucăți de implementare cu proprietar și oră-țintă. Deciziile de design sunt deja luate în `docs/DESIGN_SPEC.md` §16; nu le redeschide fără omul care le-a luat.
- **Echipa:** Tu (ML + decizie + plan) și Alina (simulator + pipeline + stare + UI). Agenții scriu codul, omul verifică și face merge.
- **Regulile obligatorii sunt în `AGENTS.md`:** doar FastAPI + React, nicio bibliotecă în afara listei, niciun fișier sursă peste 30 KB.
- **Skill-uri de folosit:** pentru întrebări deschise, `grilling` + `domain-modeling`; pentru fapte, `research`; pentru „cum arată/cum se comportă”, `prototype`. Vocabularul e în `GLOSSARY.md`.
- **Agenți ECC utili:** `ecc:fastapi-reviewer`, `ecc:python-reviewer`, `ecc:react-reviewer`, `ecc:typescript-reviewer`, `ecc:mle-reviewer`, `ecc:e2e-runner`, `ecc:build-error-resolver`.
- **Puncte de control:** H2 contracte · H5 date Raptor · H8 cap-coadă pe baseline · H12 model v1 + ordine de lucru · H17 funcții de bază · H20 code freeze · H21–24 README, slide-uri, video, repetiție.
- **Somn, niciodată simultan:** Alina H10–12:30, Tu H13–15:30.
- **La ratare:** H8 ratat cu > 1 h → Grad-CAM devine opțional. H17 ratat → TicketInbox și consistency check-ul devin opționale.
- **Cum iei un tichet:** în Claude, `/wayfinder .scratch/solartriage/map.md`, sau „ia următorul tichet deblocat cu Owner: <numele tău>”. Setează `Status: claimed` înainte de orice lucru.

## Decisions so far

<!-- o linie per tichet închis: [titlu](issues/NN-slug.md): rezumat -->

- [Python 3.15 merge cu PyTorch, ONNX Runtime și numpy?](issues/01-python-compat.md): nu, pentru onnxruntime și PyYAML. Fixăm Python 3.14 prin uv, care îl descarcă singur.
- [Formatul exact al dataset-ului InfraredSolarModules](issues/02-raptor-format.md): zip de 15,5 MB, JSON id → clasă, imagini 24×40 gri; numărătorile reale diferă de paper; 6 perechi de duplicate conflictuale de eliminat; licență MIT.
- [Instalează Node 22+ pe laptopul tău](issues/03-node-tu.md): Node v26.13.0 instalat, frontend-ul se compilează; Playwright MCP se verifică după repornirea Claude.
- [Scheme Pydantic, mock-uri FastAPI și schelet React cu tipuri generate](issues/05-contracte.md): cele 25 de endpoint-uri din §9 servesc mock-uri validate de `test_contracts.py`, React afișează parcul de 480 de module; deschise: schema `/score`, payload-urile SSE, `gen:types` prin npx cu TS 5.
- [Date ML: descărcare Raptor, dedup, split, mapare 12→8](issues/06-date-ml.md): `ml/data.py` + `ml/splits/*.csv` în repo; 19.944 de imagini după dedup (exacte + aproape-duplicate prin RMS pe pixeli, dHash respins), split 70/15/15 pe grupuri, seed 42; simulatorul citește `ml/splits/test.csv`.
- [Strat de decizie: reguli YAML, pierdere, ordine de lucru, review](issues/11-decizie.md): `decision_rules.yaml` + `loss.yaml` + PVGIS real (1.298 kWh/kWp/an, 36°); funcții pure în `services/decision/`, `rule_applied` citează regula YAML; review → ordin / fără ordin / reinspecție; CSV-uri gata; decis: scorul rămâne pondere × pierdere ca în spec, criticele ajung în ziua 1 prin planner.
- [Baseline: trăsături, reguli extinse la 8 clase, Random Forest](issues/07-baseline.md): 17 trăsături de intensitate în `backend/app/services/baseline/`, reguli în ordine fixă cu praguri ajustate pe train (`backend/config/baseline_rules.json`); macro-F1 pe val: reguli 0,367, RF 0,530.
- [ResNet18 pe Kaggle → model.onnx](issues/08-resnet-onnx.md): `ml/train.py` + `export_onnx.py` + notebook Kaggle (repo privat → `ml/` ca dataset); preprocesarea e în graf, intrare `(batch,1,40,24)` = pixel/255; v1 de pe Kaggle (20 de epoci, val macro-F1 0,642) e în `backend/artifacts/`; confuzia principală e ok → module_offline.
- [Acces GitHub și setup pe laptopul Alinei](issues/04-alina-setup.md): setup-ul trece cap-coadă pe Windows (Python 3.14 prin uv, 32 de teste, build-ul React, aplicația pe :5173 cu parcul din API); în Claude merg skill-urile, Playwright MCP și pluginul ECC.
- [Simulator în FastAPI: parc, compunere Raptor, 2 treceri, artefacte](issues/16-simulator.md): `services/sim/` (`park`, `compose`, `artefacts`), determinist din seed, toate injectările din `MissionSettings`; `/park`, `/frames` și thumbnail-urile servesc simulatorul; cu k = 0,15 niciun hot cell nu atinge ΔT 20 K (p90 13 K), deci k rămâne de decis.
- [Modelul în pipeline: /api/analyse, inferență, incertitudine](issues/10-model-analyse.md): modelul ONNX se încarcă în `lifespan`; `services/pipeline/infer.py` (batch, softmax(z/T)) + `calibrate.py` (`unsure` pe grup de severitate, valori implicite până vine 09); `/api/analyse` e real; pipeline-ul misiunii (17) apelează `calibrate.predictions(infer.probs(...))` în locul baseline-ului.
- [Planner greedy (capacitate, deplasare, grupare, motiv)](issues/12-planner.md): `services/decision/planner.py`, funcții pure, config în `decision_rules.yaml › planner` (5 zile, 7 h/echipă, deplasare 0/10/20 min); criticele primele în ziua 1, grupare pe masă apoi rând, first-fit pe zile, `reason` pe fiecare sarcină; `GET /missions/{id}/plan` e real; meteo rămâne pentru tichetul 28.
- [Calibrare (temperature scaling) și praguri pe severitate](issues/09-calibrare.md): T = 1,68, ECE pe val 0,105 → 0,023; prag `min_conf` pe clasă cu țintă pe grup (risc 98%, rest 95%), ok cu risc > 0,15 → unsure; pe val 46,8% trec automat la 96,1% precizie, ok→module_offline 0/202 trec; hot_cell, multi_hot, module_offline, soiling merg mereu la inginer cu v1.
- [pytest: cele 6 cazuri de robustețe și regula de 30 KB](issues/22-pytest-robustete.md): `backend/tests/test_robustness.py` rulează cele 6 cazuri din §6 cap-coadă pe simulator + pipeline (45 de reflexii de glare în coadă, 0 finding-uri; GPS identic cu zborul aliniat); `test_file_size.py` verifică acum și `.j2`.
- [Grad-CAM pe crop](issues/14-gradcam.md): torch CPU în backend doar pentru Grad-CAM, `best.pt` în `backend/artifacts/` (logits = ONNX la 1e-5); `services/explain/gradcam.py` pe **layer3** (layer4 e 2×3, prea grosier pentru o treime), cu ponderare grad × act; pe 250 de crop-uri de diodă din val, 0,48 din căldură cade pe banda caldă (uniform 0,33); `gradcam.png` e real, cu cache în `backend/cache/gradcam/`, model încărcat leneș.
- [Pipeline: data check, înregistrare GPS, consistency check](issues/17-pipeline-check.md): `check.py` respinge cadrele din §5 și dă mesele `not_inspected` cu motiv; `register.py` găsește coloana de sol (±1 modul, pozițiile 1/7 sau 6/12 fără imagine) și realiniază sloturile; `consistency.py` face reflexie probabilă + coadă + urgență low din anomalia văzută într-o singură trecere; `/frames` completează `check_ok`/`problems`/`gps_offset_detected`; cap-coadă cu modelul, 45/46 de module cu glare ajung în coadă și 0 în altă parte.
- [evaluate.py, reports/eval.json și figuri](issues/15-evaluate.md): pe test, o rulare: macro-F1 reguli 0,374 · RF 0,541 · ResNet18 0,657; ECE 0,101 → 0,013 (T 1,68); pragurile trec automat 48,8% la 97,1% precizie; top confuzie ok → module_offline (166); schemă `EvalReport` nouă pentru `/api/eval`; pe 12 clase doar recall; robustețea §6 vine cu 22, degradarea cu 31.
- [React: PriorityList și PlanView](issues/13-ui-plan.md): tab-ul `/plan` cu `PriorityList` (scor, urgență, kWh/zi, `rule_applied`, review, CSV descărcat din FastAPI) și `PlanView` (zile × echipe, `reason` pe sarcină); după review lista și planul se reîncarcă din API; FastAPI neschimbat; e2e `npm run e2e` pe :8100/:5180 (confirmă F-004 → WO-004 apare în ziua 1).
- [Starea misiunii: SQLite, SSE, endpoint-urile de misiune](issues/18-stare-sse.md): `models/mission.py` (fază + status în SQLite, „flying” doar în memorie), `services/state.py` (evenimente, cadre, zbor), `services/missions.py`; SSE numerotat cu `id:`, reluat din `Last-Event-ID`, închis când misiunea e inactivă; `StreamEvent` e o uniune tipată după `type`; fly/refly/analyse dau 409 pe fază greșită; 3 demo-uri cu seed fix; după merge-ul cu 17, `fly` folosește `check.frame` (mesele fără cadru valid devin `not_inspected` + re-zbor), iar `/frames` completează `check_ok`/`problems`/`gps_offset_detected`; `analyse` încă folosește findings mock până se rezolvă factorul k.
- [React: ParkMap, DronePlayer, FrameStrip, PhasePanel, useMissionStream](issues/19-ui-harta.md): ecranul `/` cu harta pe canvas (status, urgență, nesigur, reflexie probabilă, neinspectat hașurat, adevăr, dronă + amprentă), banda de cadre și pașii setări → zbor → verificare → analiză → review; store-ul scris doar din `useMissionStream` (SSE + un resync pe `GET /missions/{id}`); merge pe mock-uri, așteaptă SSE-ul real din 18; e2e `map.spec.ts`.
- [Alerte, webhook cu receptor mock, jurnalul agentului](issues/20-alerte-webhook.md): `services/decision/alerts.py` derivă alertele din regula de siguranță (ΔT ≥ 20 K) și le persistă în SQLite; fiecare alertă/ordin pleacă la `WEBHOOK_URL` cu 3 încercări logate; `analyse` emite `alert_raised` pe SSE și jurnalizează alerta, ordinele și rezultatul webhook-ului; `/alerts`, `/events`, `/ack` citesc datele misiunii.

## Not yet specified

- **Factorul `k` din conversia intensitate → temperatură aparentă:** se poate fixa doar după ce vedem distribuția reală a crop-urilor (tichetele 2 și 6) și pragul de alertă de 20 K pe ea.
- **Conținutul exact al celor 3 scenarii demo** (ce defecte, unde, care injectări): se fixează după ce simulatorul și modelul rulează (tichetele 16 și 10).
- **Narațiunea slide-urilor și cifrele-cheie:** după `eval.json`.

## Out of scope

- Agentul RL pentru baterii de pe branch-ul `feat/rl-agent`: alt proiect, neatins.
- YOLO / detecție de panouri, clasificator RGB și fuziune, PDF, ServiceNow, retrain sau ajustarea pragurilor live, orice stack în afară de FastAPI + React.
