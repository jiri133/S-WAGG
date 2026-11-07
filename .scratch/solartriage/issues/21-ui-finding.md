# React: FindingCard, ReviewQueue, AlertBanner, TicketInbox, AgentTimeline, ReportView, EvalView

Type: task
Status: claimed
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
