# Code freeze H20: verificare cap-coadă

Type: task
Status: resolved
Owner: Tu + Alina
Țintă: H20
Blocked by: 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23

## Question

Checklist:

- cele 3 scenarii rulează fără erori;
- `pytest`, `npm run build` și Playwright trec;
- `evaluate.py` regenerează cifrele;
- niciun fișier peste 30 KB;
- totul e în `main`.

De aici, doar fix-uri. Tichetele opționale 27–31 se deblochează doar dacă checklist-ul e verde și rămâne timp.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

## Answer

Verificat pe `docs/design-spec` @ `3daaf2e`, cu dataset-ul Raptor real descărcat local (`data/raptor/`, 20.000 crop-uri, SHA-256 `b82c706b…` verificat; toate cele 2.977 căi din `ml/splits/test.csv` există). Am repornit backend-ul ca `compose.crops()` să folosească imaginile reale (`median_ok = 156`).

- **Cele 3 scenarii:** `frontend/e2e/scenarios.spec.ts` rulează `normal`, `bad_day` și `explain` prin UI + FastAPI; `npm run e2e` → **7 passed** (3 scenarii + 4 spec-uri existente, 3,3 min).
- **pytest / build / Playwright:** `cd backend && uv run pytest -q` → **192 passed, 0 skipped** (testul crop-urilor reale rulează acum); `uv run ruff check .` → curat; `cd frontend && npm run build` și `npm run lint` → verzi; `npm run e2e` → 7 passed.
- **`evaluate.py`:** `PYTHONUTF8=1 uv run --project backend python evaluate.py` → rules **0.374**, RF **0.541**, ResNet18 **0.706** macro-F1 pe test; ECE 0.048 → 0.015 (T=1.36); coverage automată 0.601 la precizie 0.960 (țintă 0.95). `reports/eval.json` regenerat diferă doar în ultimele zecimale float, așa că am păstrat fișierul commit-uit.
- **Regula de 30 KB:** `tests/test_file_size.py` trece; acoperă acum și template-urile `.j2` (ticket 22). Niciun fișier sursă peste 30.720 bytes.
- **`main`:** tot codul e pe `docs/design-spec` (push-uit la `3daaf2e`); merge-ul final în `main` rămâne pentru om, conform `AGENTS.md` (agenții nu fac commit pe `main`). Checklist-ul de funcționalitate e verde pe branch-ul de integrare.

### Depinde de

- [Date ML: descărcare Raptor, dedup, split, mapare 12→8](06-date-ml.md)
- [Baseline: trăsături, reguli extinse la 8 clase, Random Forest](07-baseline.md)
- [ResNet18 pe Kaggle → model.onnx](08-resnet-onnx.md)
- [Calibrare (temperature scaling) și praguri pe severitate](09-calibrare.md)
- [Modelul în pipeline: /api/analyse, inferență, incertitudine](10-model-analyse.md)
- [Strat de decizie: reguli YAML, pierdere, ordine de lucru, review](11-decizie.md)
- [Planner greedy (capacitate, deplasare, grupare, motiv)](12-planner.md)
- [React: PriorityList și PlanView](13-ui-plan.md)
- [Grad-CAM pe crop](14-gradcam.md)
- [evaluate.py, reports/eval.json și figuri](15-evaluate.md)
- [Simulator în FastAPI: parc, compunere Raptor, 2 treceri, artefacte](16-simulator.md)
- [Pipeline: data check, înregistrare GPS, consistency check](17-pipeline-check.md)
- [Starea misiunii: SQLite, SSE, endpoint-urile de misiune](18-stare-sse.md)
- [React: ParkMap, DronePlayer, FrameStrip, PhasePanel, useMissionStream](19-ui-harta.md)
- [Alerte, webhook cu receptor mock, jurnalul agentului](20-alerte-webhook.md)
- [React: FindingCard, ReviewQueue, AlertBanner, TicketInbox, AgentTimeline, ReportView, EvalView](21-ui-finding.md)
- [pytest: cele 6 cazuri de robustețe și regula de 30 KB](22-pytest-robustete.md)
- [Teste Playwright E2E pe cele 3 scenarii de demo](23-playwright-e2e.md)
