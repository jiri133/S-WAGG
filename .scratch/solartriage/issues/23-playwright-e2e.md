# Teste Playwright E2E pe cele 3 scenarii de demo

Type: task
Status: open
Owner: Alina
Țintă: H19
Blocked by: 19, 21

## Question

`npm i -D @playwright/test`, apoi `frontend/e2e/` cu câte un test pentru fiecare scenariu din §12 (pornesc prin `POST /api/missions/demo/{scenario}`). Se pot genera cu agentul `ecc:e2e-runner`.

**Gata când:** `npx playwright test` trece cu backend-ul și frontend-ul pornite.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [React: ParkMap, DronePlayer, FrameStrip, PhasePanel, useMissionStream](19-ui-harta.md)
- [React: FindingCard, ReviewQueue, AlertBanner, TicketInbox, AgentTimeline, ReportView, EvalView](21-ui-finding.md)
