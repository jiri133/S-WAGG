# Code freeze H20: verificare cap-coadă

Type: task
Status: open
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
