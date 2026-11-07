# Teste Playwright E2E pe cele 3 scenarii de demo

Type: task
Status: resolved
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

## Answer

**Ce am făcut**

- `frontend/e2e/scenarios.spec.ts` (nou, ~8,9 KB, 3 teste) — câte un test pentru fiecare scenariu din `DESIGN_SPEC` §12, prin React + FastAPI:
  - **normal**: `POST /api/missions/demo/normal` → zbor → verificare date → analiză → banner `AL-001`, „Alertă critică” în jurnal, tichet în inbox-ul mock → card de finding cu crop, Grad-CAM (`naturalWidth > 0`), ΔT 12,6 K și regula din `decision_rules.yaml` → tab-urile Plan și Evaluare (Reguli / Random Forest / ResNet18).
  - **bad day**: zbor → cadrele respinse sunt listate cu motiv (`nu e radiometric` pentru RGB, `nicio grilă de module`, iradianță < 600) → `not_inspected > 0` (8 mese = 96 module la seed 11) și butonul `Re-zbor` → re-zbor doar pe mesele neinspectate → faza revine la `checked`, `0 module neinspectate`, apoi analiza ridică alerta și trimite `WO-001` în inbox.
  - **explain**: zbor curat (`0 respinse`) → analiză → evidence-ul finding-ului de diodă F-002 (modul `B1-R4-T1-M03`, clasă `diode_substring`, ΔT 9,8 K, regulă) și Grad-CAM-ul lui servit de FastAPI → cardul finding-ului nesigur F-004 (Grad-CAM, ΔT 12,6 K) → pe tab-ul Plan: `Respinge` (WO-004 dispare) apoi `Confirmă` (WO-004 reapare; planul se reface) → Evaluare cu cele 3 modele.
- Pornirea fără UI de demo: testul cheamă direct `POST /api/missions/demo/{scenario}`, apoi răspunde la `POST /api/missions` al aplicației (butonul „Creează misiunea”) cu misiunea demo; store-ul primește `demo-{scenario}`, iar fly/check/analyse merg pe id-ul demo. Nu am adăugat butoane în produs.
- Review-urile din `mock_data` sunt stare globală în procesul FastAPI, iar spec-urile anterioare îl lasă pe F-004 revizuit; testele de scenariu citesc `GET /missions/{id}/findings` fără review-ul salvat (ruta de POST rămâne neatinsă), ca să nu depindă de ordinea spec-urilor.
- Zborurile demo păstrează viteza din seed (1×, ~42 s); fișierul are `test.describe.configure({ timeout: 150_000 })` și 90 s pentru „Zbor terminat”. Nu am atins `playwright.config.ts` (pornirea backend :8100 + Vite :5180 era deja corectă).

**Cum am verificat**

- `cd frontend && npx playwright test scenarios.spec.ts` → **3 passed (3.0m)** (normal, bad day 56,2 s, explain 49,0 s).
- `cd frontend && npm run e2e` → **7 passed (3.5m)**: cele 4 spec-uri existente + cele 3 noi, aceleași comenzi care pornesc FastAPI :8100 și Vite :5180.
- `cd frontend && npm run build` → **✓ built in 895ms** (doar avertismentul Vite de chunk > 500 kB).
- `cd frontend && npm run lint` → fără avertismente.
- `cd backend && uv run pytest -q` → **191 passed, 1 skipped in 86.66s**.
- `cd backend && uv run ruff check .` → **All checks passed!**
- Backend-ul nu a fost modificat.

**De știut**

- Analiza folosește încă finding-urile mock F-001..F-005 (`services/missions.py`; k nu e fixat), deci testele verifică ce expune UI/API acum, nu cifrele din §12 (14 finding-uri etc.): 5 finding-uri, 1 critical, 1 nesigur. Când pipeline-ul real e legat, aserțiunile pe clase/numere trebuie revizuite.
- În UI cardul se deschide doar pentru finding-urile `nesigure` (ReviewQueue). F-002 (dioda) nu e nesigur, deci clasa/ΔT/regula/Grad-CAM-ul lui sunt verificate prin FastAPI + tabelul de priorități, iar cardul (crop + Grad-CAM) pe F-004. E o limitare a UI/mock-ului, nu a testului.
- La Re-zbor, SSE se reconectează fără `Last-Event-ID`, serverul replays toate evenimentele, iar `FrameStrip` vede temporar chei duplicate (warning React în consola Vite); resync-ul final rescrie lista din API. Testul trece, dar e un bug preexistent de replay SSE, nu l-am reparat (în afara tichetului de teste).
- Glare/GPS din §12 nu sunt expuse de UI (nu există verdict/coloană pentru ele; glare nu e clasă), deci nu sunt asertate.
- `npm run e2e` rescrie `reports/19-harta-dupa-analiza.png` (map.spec); nu l-am comis.
