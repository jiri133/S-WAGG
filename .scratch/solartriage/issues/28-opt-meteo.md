# Opțional: meteo în planner

Type: task
Status: resolved
Owner: Tu
Țintă: după H20
Blocked by: 24

## Question

Spec: §7. `config/weather.json` pe 5 zile: electricienii nu lucrează pe ploaie, curățenia nu lucrează pe vânt > 10 m/s.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Code freeze H20: verificare cap-coadă](24-code-freeze.md)

## Answer

**Ce s-a construit (FastAPI, `backend/app/services/decision/planner.py`):**

- `backend/config/weather.json`: prognoză fixă pe 5 zile, offline (8–12 noiembrie): ziua 2 ploaie, ziua 3 vânt 12 m/s, restul senin/noros.
- Regula din §7: `closed(day, crew)`: electricienii nu lucrează pe ploaie, curățenia nu lucrează pe vânt > `planner.cleaning_max_wind_ms` (10 m/s, în `decision_rules.yaml`). O echipă oprită are capacitatea 0 în ziua aceea, deci sarcinile ei trec în următoarea zi cu vreme bună.
- `PlanDay.weather` arată prognoza („ploaie, vânt 6 m/s”), iar `capacity_h` e 0 pentru echipa oprită. Motivul sarcinii spune de ce a fost mutată: „ziua 2: ploaie, vânt 6 m/s, echipa electrical nu lucrează”.
- `plan(..., weather=None)` citește `weather.json`; testele pot da altă prognoză.
- React `PlanView`: o echipă oprită apare ca „nu lucrează (meteo)”.

**Cum am verificat:**

- `cd backend && uv run pytest -q` → 214 passed. Teste noi în `test_planner.py`: `test_no_electrical_work_in_the_rain_and_no_cleaning_in_strong_wind` și `test_clear_week_keeps_full_capacity_every_day`. `uv run ruff check .` → curat.
- Scenariul 1 cap-coadă (zbor + analiză + `GET /api/missions/demo-normal/plan`):
  - ziua 1: 22 de sarcini;
  - ziua 2 (ploaie): electrical 0/0 h, nicio sarcină (curățenia n-a avut nimic de făcut);
  - ziua 3 (vânt 12 m/s): curățenia 0 h, electrical 6,83 h;
  - zilele 4–5: lucrări electrice;
  - 11 ordine neprogramate în 5 zile.
- `npm run build` verde; `npx playwright test e2e/plan.spec.ts` → passed, cu verificarea că ziua 2 conține „ploaie” și „nu lucrează (meteo)”.
