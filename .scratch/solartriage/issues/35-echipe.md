# Echipe concrete în planner: oameni, competențe, ture, zile libere

Type: task
Status: resolved
Owner: Tu
Țintă: după H20
Blocked by: 28

## Question

Decizia omului: „Da, adaugă-l” la lista de echipe în planner. Ce echipă se trimite și când, în funcție de vreme, de disponibilitatea oamenilor, de programul de lucru și de echipă. Fără un al doilea model: se face pe date și reguli (ADR 0001, §7).

## Answer

**Ce s-a construit (FastAPI, `backend/app/services/decision/planner.py`):**

- `backend/config/crews.yaml`, cu 3 echipe:
  - E1, electricieni de gardă: lucrează L–D, 08:00–15:00, toate piesele;
  - E2, electricieni: lucrează L–V, 07:00–15:00, doar diode și conectori, în concediu pe 2026-11-11;
  - C1, curățenie: lucrează L–S, 09:00–15:00.

  Fiecare echipă are oameni, competențe (piesele din `decision_rules.yaml`), oră de start, ore pe zi, zile de lucru și `days_off`. `capacity_h` din `decision_rules.yaml` a fost scos.
- `can_do`: un ordin merge doar la o echipă de tipul cerut care știe piesa; un ordin fără piesă merge la orice echipă de tipul lui.
- `why_off`: o echipă nu lucrează într-o zi din cauza vremii (§7, tichetul 28), pentru că nu e zi de lucru pentru ea sau pentru că e în concediu.
- Greedy-ul pune fiecare sarcină în prima zi în care o echipă capabilă mai are timp.
- `PlanTask` are acum `crew` (ID-ul echipei), `people` și `start` (ora din tură). `PlanDay.off` spune de ce nu lucrează o echipă, iar `Plan.crews` dă legenda.
- Motivul sarcinii spune echipa și de ce a fost mutată: „doar E1 schimbă „modul””, „ziua 1: E2 nu lucrează duminică”, „ziua 2: ploaie, vânt 6 m/s, echipa electrical nu lucrează”.
- React `PlanView`: legenda echipelor (tip, tură, oameni, piese), 3 coloane pe zi, „nu lucrează: <motiv>” și ora de start a fiecărei sarcini.
- Spec §7 actualizat.

**Cum am verificat:**

- `cd backend && uv run pytest -q` → verde, `uv run ruff check .` → curat.
  - Testele vechi ale planner-ului rulează pe o listă cu o echipă de fiecare tip, mereu disponibilă (`ONE`), deci regulile de capacitate, critice și grupare sunt aceleași.
  - Teste noi: `test_crews_work_only_on_their_days_and_shifts`, `test_module_swaps_go_only_to_crews_that_can_change_modules`, `test_clock_adds_hours_to_the_shift_start`.
- Scenariul 1 în React (`npx playwright test e2e/plan.spec.ts`, captura în `reports/35-plan-echipe.png`):
  - duminică lucrează doar E1, cu alertele critice primele la 08:00;
  - luni plouă: E1 și E2 stau acasă, C1 face 16 curățări;
  - joi E2 e în concediu;
  - schimburile de module merg doar la E1.
- 11 ordine rămân neprogramate în 5 zile. Sunt schimburi de module pe care doar E1 le poate face, iar E2 stă liber în ziua 5. Asta e de discutat cu omul: ori E2 primește competența „modul”, ori se adaugă o echipă.
