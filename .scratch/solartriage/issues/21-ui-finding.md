# React: FindingCard, ReviewQueue, AlertBanner, TicketInbox, AgentTimeline, ReportView, EvalView

Type: task
Status: resolved
Owner: Alina
Țintă: H17
Blocked by: 14, 15, 19, 20

## Question

Spec: §8, §10 și §3.5.

- Cardul cu crop, Grad-CAM, ΔT, pattern, regula aplicată și butoanele de review.
- Coada „nu sunt sigur”, banner-ul de alertă, inbox-ul de tichete, timeline-ul agentului.
- Raportul: template Jinja2 `services/report/report.html.j2` + `GET /api/missions/{id}/report`, afișat în iframe.
- Tab-ul de evaluare din `eval.json`.

**Gata când:** scenariul 3 din §12 se poate parcurge integral în UI.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Grad-CAM pe crop](14-gradcam.md)
- [evaluate.py, reports/eval.json și figuri](15-evaluate.md)
- [React: ParkMap, DronePlayer, FrameStrip, PhasePanel, useMissionStream](19-ui-harta.md)
- [Alerte, webhook cu receptor mock, jurnalul agentului](20-alerte-webhook.md)

## Answer

**Ce e făcut:**

- `components/FindingCard.tsx`: crop și Grad-CAM din `urls.crop/gradcam` (imaginile vin din FastAPI), ΔT aparent, pattern, `rule_applied`, predicție cu probabilitate, baseline, adevărul de teren când misiunea e demo, motivul „nesigur” și butoanele Confirmă / Respinge / Neconcludent prin `solarApi.review`.
- `components/ReviewQueue.tsx`: finding-urile `unsure` fără review; deschid cardul sau se pot revizui direct din coadă. După review ies din coadă.
- `components/AlertBanner.tsx`: alertele critice ale misiunii din `GET /missions/{id}/alerts`, cu `POST /alerts/{id}/ack`; banner-ul dispare după confirmare (starea ack-uită e ținută pe misiune, ca una nouă să pornească curat).
- `components/TicketInbox.tsx`: `GET /api/mock/ticketing`, tichetele primite de webhook (alertă vs. ordin după prezența câmpului `level`).
- `components/AgentTimeline.tsx`: `GET /missions/{id}/events`, în ordinea în care le-a scris agentul (cele mai vechi primele), cu `kind`, `message` și `ref`.
- `components/ReportView.tsx` + `pages/Report.tsx`: iframe pe `urls.report(missionId)`.
- `components/EvalView.tsx` + `pages/Eval.tsx`: `GET /api/eval` cu Recharts — bare pentru macro-F1 (Reguli / Random Forest / ResNet18), tabel cu macro-F1 și acuratețe, ECE înainte/după cu temperatura, matricea de confuzie a modelului principal și top confuzii.
- `pages/Main.tsx`: banner sus; stânga `ParkMap` + `FrameStrip`; dreapta `PhasePanel` sau `FindingCard` (la selecție) plus `ReviewQueue`; jos `AgentTimeline` + `TicketInbox`. `useMissionStream.ts` are acum `missionActions.review`, care după review recitește finding-urile, ordinele de lucru și planul (ca pagina Plan), apoi scrie finding-urile în store.
- `App.tsx` + `Layout.tsx`: tab-urile `/plan`, `/raport`, `/evaluare` (plus Status-ul existent).
- Backend: `services/report/__init__.py` + `services/report/report.html.j2` (Jinja2, 3,3 KB) randau raportul cu finding-urile, ordinele de lucru, planul și alertele misiunii; `GET /missions/{id}/report` întoarce acum HTML-ul din template. `mock_data.report_html` (mock-ul vechi) a fost șters.
- `e2e/finding.spec.ts`: scenariul 3 din §12 cap-coadă.

**Cum am verificat:**

- `cd backend && uv run pytest -q` → `191 passed, 1 skipped in 40.84s` (inclusiv `test_contracts` extins: raportul conține misiunea, finding-ul, ordinele de lucru și planul; `test_file_size` trece cu template-ul `.j2` nou).
- `cd backend && uv run ruff check .` → `All checks passed!`.
- `cd frontend && npm run build` → `✓ built in 805ms`. Vite dă doar avertismentul de chunk > 500 KB (Recharts), fără erori. Schemele Pydantic nu s-au schimbat, deci `types.gen.ts` a rămas neatins.
- `cd frontend && npm run lint` → fără avertismente.
- `cd frontend && npm run e2e` → `4 passed (57.5s)`. Noul test parcurge: zbor la 5× → verificare → analiză → card F-004 (crop și Grad-CAM încărcate, `naturalWidth > 0`) → `Confirmă` (coada se golește) → `Confirmă primirea` (banner-ul dispare) → jurnalul și inbox-ul conțin `AL-001`/`WO-001` → planul arată `task-WO-004` → iframe-ul raportului conține titlul, finding-ul și alerta → tab-ul Evaluare arată Reguli / Random Forest / ResNet18, graficul macro-F1, matricea de confuzie și ECE. Cele 3 teste existente trec neschimbate.

**De știut:**

- `playwright.config.ts` rulează acum cu `workers: 1`: un singur proces FastAPI servește toată suita, iar finding-urile și review-urile mock sunt stare globală în memorie; `plan.spec` și noul spec își confirmau F-004 simultan la 3 workers.
- În config-ul Playwright backend-ul pornește cu `WEBHOOK_URL=http://localhost:8100/api/mock/ticketing`; implicitul e `:8000`, deci altfel tichetele nu ajung în inbox-ul mock din suita de e2e.
- Raportul și inbox-ul folosesc tot datele mock existente (pipeline-ul real rămâne pe tichetul 17), iar finding-urile sunt globale, ca în restul rutelor de până acum.
- Payload-urile din `/api/mock/ticketing` nu au tip generat; `TicketInbox` le citește ca `Record<string, unknown>` și distinge alerta de ordin prin câmpul `level`.
