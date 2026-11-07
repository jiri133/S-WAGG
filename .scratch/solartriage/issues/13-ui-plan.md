# React: PriorityList și PlanView

Type: task
Status: resolved
Owner: Tu
Țintă: H17
Blocked by: 11, 12

## Question

Spec: §10. Lista de priorități (scor, urgență, pierdere, descărcare CSV) și planul pe zile și echipe, cu motivul fiecărei sarcini (Recharts dacă ajută).

**Gata când:** confirmarea unui finding în review reface planul vizibil în UI.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Strat de decizie: reguli YAML, pierdere, ordine de lucru, review](11-decizie.md)
- [Planner greedy (capacitate, deplasare, grupare, motiv)](12-planner.md)

## Answer

**Ce e construit** (doar React; FastAPI n-a avut nevoie de schimbări, `GET /missions/{id}/plan` reface deja planul din review-uri)

- `frontend/src/components/PriorityList.tsx`: finding-urile de la `GET /missions/{id}/findings` (deja sortate după scor în FastAPI), cu modul, defect (+ „nesigur”), urgență colorată, pierdere kWh/zi, scor, motivul (`evidence.rule_applied`) și 3 butoane de review (Confirmă / Respinge / Neconcludent). Linkul „Descarcă ordinele de lucru (CSV)” descarcă direct `GET /missions/{id}/work-orders?format=csv`; React nu construiește CSV.
- `frontend/src/components/PlanView.tsx`: planul pe zile, cu câte o coloană pe echipă (ore folosite / capacitate), sarcinile cu start, durată, ordin de lucru și `reason`, pierderea evitată și lista neprogramatelor.
- `frontend/src/pages/Plan.tsx`: tab-ul Plan (§10). După `POST /findings/{id}/review` reîncarcă finding-urile și planul din API. Id-ul misiunii vine din `missionStore` (citit, nu modificat), cu `M-0001` implicit până vine starea misiunii (18).
- Fișiere comune, doar minimul: o rută `/plan` + un import în `App.tsx`, un `NavLink` „Plan” în `Layout.tsx`. `Main.tsx` și store-ul sunt neatinse.
- Tipurile vin din `types.gen.ts` prin `api.ts` (`Finding`, `ReviewIn`, `Plan`). Niciun tip scris de mână.
- e2e: `@playwright/test` (devDependency), `frontend/playwright.config.ts` pornește propriul FastAPI pe :8100 și Vite pe :5180 (cu `VITE_PROXY_TARGET`), ca să nu lovească serverele de dev de pe 8000/5173. `npm run e2e`. Testul `e2e/plan.spec.ts`: respinge F-004 (WO-004 nu e în plan), apoi confirmă F-004 → WO-004 apare în plan. Prima respingere face testul repetabil, fiindcă review-urile stau în memoria backend-ului.

**Cum am verificat**

- `cd backend && uv run pytest -q` → `140 passed, 1 skipped` (include `test_file_size.py`). `uv run ruff check` → `All checks passed!`.
- `cd frontend && npm run build` → `✓ built`. `npm run e2e` → `1 passed`.
- Aplicația pornită (FastAPI :8100 + Vite :5180), pagina `/plan` deschisă cu Playwright MCP. Înainte: ziua 1 are WO-001 (critică, „alertă critică de siguranță…”), WO-003, WO-002 la electricieni (4,7 / 7,0 h) și WO-005 la curățenie; pierdere evitată 50,6 kWh. Click „Confirmă” pe F-004 (multi_hot, nesigur) → WO-004 apare la 5,0 h în ziua 1 („urgență medium, scor 0.234 (locul 4 în prioritate); deplasare 20 min”), electricienii 7,0 / 7,0 h, pierdere evitată 54,1 kWh. Screenshot-uri: `reports/13-plan-before.png`, `reports/13-plan-after-confirm.png`.
- CSV prin proxy: `curl .../api/missions/M-0001/work-orders?format=csv` → 200, `text/csv`, `attachment; filename="work-orders-M-0001.csv"`.
- Neverificat: zilele 2–5 sunt goale în mock (5 ordine încap în ziua 1); afișarea pe mai multe zile se vede abia cu datele din pipeline (17).
