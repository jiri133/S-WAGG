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

## Not yet specified

- **Factorul `k` din conversia intensitate → temperatură aparentă:** se poate fixa doar după ce vedem distribuția reală a crop-urilor (tichetele 2 și 6) și pragul de alertă de 20 K pe ea.
- **Conținutul exact al celor 3 scenarii demo** (ce defecte, unde, care injectări): se fixează după ce simulatorul și modelul rulează (tichetele 16 și 10).
- **Narațiunea slide-urilor și cifrele-cheie:** după `eval.json`.

## Out of scope

- Agentul RL pentru baterii de pe branch-ul `feat/rl-agent`: alt proiect, neatins.
- YOLO / detecție de panouri, clasificator RGB și fuziune, PDF, ServiceNow, retrain sau ajustarea pragurilor live, orice stack în afară de FastAPI + React.
