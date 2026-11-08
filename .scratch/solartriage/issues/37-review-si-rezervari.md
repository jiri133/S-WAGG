# Review cu efect vizibil și planuri aprobate care țin echipele ocupate

Type: task
Status: resolved
Owner: Tu
Țintă: după H20
Blocked by: 35, 36

## Question

Cererile omului:
1. „Vreau să se întâmple ceva cu ele dacă apăs pe butoane.”
2. „Să-mi scoată din nesigure dacă e sigur.”
3. „Menține datele în baza de date: dacă ai făcut un plan, ține minte pentru echipele alea că sunt ocupate.”

## Answer

**Review cu efect (FastAPI + React):**
- `findings.review` scrie decizia și pe harta misiunii (`MissionRow.status`): confirmat → `finding`, respins → `ok` (fără finding), neconcludent → `unsure`.
- În tab-ul Plan:
  - după fiecare click apare un mesaj, de exemplu „F-012 respins: ordinul a ieșit din plan, modulul e marcat sănătos”;
  - un finding confirmat arată „confirmat” în loc de „nesigur”;
  - cele respinse trec în lista „Respinse” (deschisă), de unde Confirmă le readuce în plan;
  - neconcludentele arată „reinspecție”.
- Pastila „nesigure” din pagina principală numără doar cele încă nedecise. Coada le scotea deja.
- Butoanele mergeau pe misiunea greșită până la commit-ul 493dca1: ID-urile se repetă între misiuni, iar acum review-ul primește `?mission_id=`.

**Planuri aprobate (SQLite, tabelul nou `plan_approval`):**
- `POST /api/missions/{id}/plan/approve` îngheață planul curent. `GET /plan` îl întoarce apoi neschimbat, cu `approved_at`.
- Orele lui pe zi și echipă sunt scăzute din capacitatea echipelor în planul **oricărei alte misiuni**. `planner.plan(busy=…)` arată orele în `PlanDay.busy_h`, iar React afișează „x h ocupate de alte planuri aprobate”.
- `DELETE …/plan/approve` eliberează echipele.
- O analiză nouă a misiunii, sau un demo pornit din nou, șterge aprobarea (`findings.clear`).
- Am pus aprobarea pe un buton explicit („Aprobă planul”), ca să nu ocupe echipele fiecare misiune sau demo rulat de probă.
- Endpoint-urile sunt noi față de §9: le-a cerut omul.

**Cum am verificat:**
- `cd backend && uv run pytest -q` → 254 passed. Teste noi:
  - `test_review_shows_on_the_missions_map`;
  - `test_an_approved_plan_keeps_its_crews_busy_for_other_missions` (capacitatea scade exact cu orele aprobate, planul aprobat nu se mișcă la un review, eliberarea scoate rezervarea).
- `uv run ruff check .` curat.
- `npm run build` verde.
- `npx playwright test` → 7 passed: `plan.spec.ts` verifică mesajul, „confirmat”, mutarea în „Respinse”, ieșirea din plan, aprobarea și anularea ei.
