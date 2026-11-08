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

### Lizibilitate (cererea omului: „afisarea si celee neprogramate + … mai citibile”)

- **Neprogramatele:** `Plan.unscheduled_why` spune pentru fiecare ordin de ce nu a fost programat, de exemplu „E1 nu mai are 2 h libere în 5 zile; doar E1 schimbă „modul””. `PlanView` le arată într-un tabel cu ordinul, modulul, defectul, urgența, echipa, piesa, orele și motivul.
- **Prioritățile:** `Finding.summary` e un rând scris în FastAPI, de exemplu „module_offline 94% · urgență high · ~1,10 kWh/zi pierduți” sau „ΔT 31,0 K ≥ 20 K: alertă de siguranță · hot_cell 100%”. `Finding.action` e verificarea din YAML. Calculul complet (`rule_applied`) stă sub „calcul”.
- **Planul:** `PlanTask.notes` e motivul pe puncte, iar `start` și `end` sunt orele din tură. Fiecare sarcină arată ora, ordinul, defectul, modulul și urgența.
- **Coada „nesigure”:** `unsure_reason` spune acum „hot_cell merge mereu la inginer (încredere 92%)”, nu „încredere 0.92 sub pragul 1.00”.
- **Verificare:** `uv run pytest -q` verde. `npx playwright test e2e/plan.spec.ts` verifică rezumatul, „calcul” și tabelul de neprogramate. Capturile sunt în `reports/35-prioritati.png` și `reports/35-plan-echipe.png`.

### După review-ul omului (re-zbor, prea multe probleme, planificare, lizibilitate)

- **Planificarea:** gruparea trăgea lucrări mici în fața celor urgente. Pe scenariul 1, WO-029 (low, locul 42) era programat, iar ordine de pe locurile 10–12 rămâneau neprogramate. Acum fiecare ordin ia prima zi liberă strict în ordinea priorității. Abia apoi ziua fiecărei echipe e ordonată pe masă și pe rând, cu criticele primele. Test nou: `test_a_lower_order_never_takes_the_place_of_a_higher_one`, care pică pe planner-ul vechi.
- **Filtrarea:** lista „de urmărit” (`Finding.watch`, `decision_rules.yaml › watch.min_p_ok: 0.10`, amendament în ADR 0001). Pe scenariul 1 rămân 19 de reparat și 27 de urmărit (înainte erau 46 de ordine), iar toate cele 19 încap în cele 5 zile.
- **Re-zborul:** un stream nou retrimite tot istoricul misiunii, deci `flight_done`-ul primului zbor ascundea drona imediat. `useMissionStream` ignoră acum evenimentele deja aplicate. e2e-ul „bad day” verifică „Drona la …” după Re-zbor.
- **Lizibilitatea:**
  - Prioritățile sunt pe un rând: urgență, modul, defect cu încrederea, ce face echipa (`decision_rules.yaml › short`), pierdere și review. Motivul, verificarea completă și calculul apar la „de ce”.
  - Sarcinile din plan sunt pe un rând: oră, urgență, defect și modul; motivul pe puncte apare la click.
- **Verificare:** `uv run pytest -q` și `npx playwright test` sunt verzi. Capturile sunt în `reports/35-prioritati.png` și `reports/35-plan-echipe.png`.

### Drona pe hartă (cererea omului: „nu urmărește parcul”, „pune cu roșu mai repede decât merge drona”)

- **Traseul:** zborul merge în șerpuire (`missions.flight_order`). Blocul 1 se parcurge rând cu rând de sus în jos, apoi Blocul 2 de jos în sus, iar fiecare rând pornește de la capătul cel mai apropiat de dronă. Înainte, la capătul fiecărui rând drona traversa înapoi la stânga. Analiza și numerotarea findings-urilor rămân pe ordinea parcului.
- **Sincronizarea:** FastAPI așteaptă cât îi ia dronei să ajungă la masă (`HOME_M`, `DRONE_M_S = 20 m/s × viteza`), iar React o desenează cu aceleași numere și fără limită de viteză. Când sosește un cadru, drona e deasupra mesei lui: în e2e, la viteza 5×, distanța e de 1 px pe rând drept și de cel mult 23 px la schimbarea de rând (o masă are 60 × 34 px).
- **Punctul de start:** e acum în interiorul hărții (-1,8 m), deci iconița nu mai e tăiată de margine.
- **Linii drepte:** între două mese, drona nu mai taie în diagonală. Merge întâi pe verticală până la rândul mesei, apoi pe orizontală de-a lungul rândului (`missions.legs`; colțul e un waypoint separat), iar timpul de zbor se calculează pe traseul în L. La final se întoarce la start tot pe linii drepte. Test: `test_drone_flies_in_straight_lines_along_rows_and_back_home`, unde toate segmentele re-zborului sunt verticale sau orizontale.
