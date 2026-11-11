# S$$$WAGG team repo

> English version: [README.md](README.md)

> De la zborul dronei la ordine de lucru în 40 de secunde, nu în săptămâni.

O dronă termică zboară peste un parc fotovoltaic. SolarTriage verifică fiecare cadru, găsește modulele defecte cu un model antrenat de noi, spune cât de sigur e și cât pierde fiecare defect. Apoi scrie ordinele de lucru și planul pe zile pentru echipe, cu meteo și turele fiecăreia. Inginerul O&M doar confirmă sau respinge.

Repo-ul are și o a doua parte, **optimizarea costurilor fermei**: prognoză PV + dispecerizarea bateriei pe piața OPCOM, în pachetul `RL/` și în tab-ul **Costuri parc**.

**Stack:** backend Python + FastAPI (simulator, pipeline, model ONNX, decizie, plan), frontend React + Vite + TypeScript. Comunică prin HTTP/JSON și SSE sub `/api`.

## Cum rulezi (3 comenzi)

Ai nevoie de [uv](https://docs.astral.sh/uv/) (descarcă singur Python) și de Node 22+.

```bash
uv run --no-project python ml/fetch_raptor.py
```

Descarcă și extrage datele Raptor (15,5 MB, verificate cu SHA-256 în `data/raptor/`). Scriptul e stdlib, deci nu instalează mediul `ml/` (nici torch). Split-urile (`ml/splits/*.csv`), modelul (`backend/artifacts/model.onnx`) și `reports/eval.json` sunt deja în repo — nu antrenezi nimic și tab-ul **Evaluare** merge ca atare. Fără crop-uri, backend-ul tot pornește, dar simulatorul folosește crop-uri sintetice și scenariile demo dau alte rezultate.

```bash
cd backend && uv sync && uv run fastapi dev app/main.py
```

```bash
cd frontend && npm install && npm run dev
```

Deschide http://localhost:5173. Documentația API (Swagger) e la http://localhost:8000/api/docs.

Pe Windows (PowerShell 5.1 nu acceptă `&&`), după `cd backend; uv sync` și `cd frontend; npm install`, pornește ambele dintr-o comandă:

```powershell
powershell -ExecutionPolicy Bypass -File .\dev.ps1
```

Pentru tab-ul **Costuri parc** e nevoie o singură dată și de mediul `RL/`: `cd RL && uv sync` (detalii în `RL/README.md`).

## Demo

Aplicația are două părți mari, în același frontend și backend:

1. **Scanarea cu drona** — de la zbor la ordine de lucru: tab-urile **Parc**, **Plan**, **Raport**, **Evaluare**.
2. **Optimizarea costurilor fermei** — dispecerizarea bateriei pe piața OPCOM: tab-ul **Costuri parc**, pe parcul activ din **Configurare parc**.

### 1. Scanarea cu drona (sub 7 minute)

În tab-ul **Parc**, pasul 1 are trei butoane **Demo**. Fiecare creează misiunea cu seed fix (`POST /api/missions/demo/{scenario}`). Apoi: **Pornește zborul** → **Verificarea datelor** → **Analizează** → **Review**.

1. **Ziua normală.** Zborul durează ~40 s, cadrele apar pe bandă și harta se colorează. Analiza găsește un hot cell cu ΔT 31 K, care dă alertă critică (banner + tichet în Inbox). În **Plan** vezi prioritățile și planul pe zilele lucrătoare (luni–vineri) de care e nevoie, cel mult 30, pe echipe concrete (`backend/config/crews.yaml`): ziua cu ploaie ține electricienii acasă, o echipă e în concediu, iar lucrul se împarte între electricienii care pot face lucrarea. Fiecare sarcină are ora, oamenii și motivul scris. Finding-urile sigure merg singure în plan, fără butoane. Doar cele din coada „nesigure” au Confirmă (intră în plan ca reparație), Respinge (finding-ul se șterge, modulul apare sănătos) și Neconcludent (o etichetă albastră „de analizat”, ordinul nu se schimbă). **Aprobă planul** îl îngheață și ține echipele ocupate în acele ore pentru planurile altor misiuni. CSV-ul se descarcă din **Plan**, raportul HTML e în **Raport**.
2. **Ziua proastă.** Nor, cadru lipsă, cadru RGB, cadru fără panouri, reflexii, eroare GPS. Mesele fără niciun cadru valid apar hașurate, cu motivul. **Re-zbor** le reface, iar GPS-ul e corectat automat.
3. **De ce are dreptate.** Fișa unui finding de diodă arată Grad-CAM, ΔT, pattern-ul, 3 cazuri similare din setul de antrenare și regula aplicată. Un caz „nesigur” are deja ordin „verifică și repară”. Dacă îl respingi, ordinul iese din plan pe loc. Tab-ul **Evaluare** arată reguli → Random Forest → ResNet18 → CNN mic, macro-F1 și matricea de confuzie, apoi prognoza PV (MAE, RMSE, bias pe split-uri) și rezultatele bateriei: scor pe strategie, costuri și telemetria LLM.

### 2. Optimizarea costurilor fermei (baterie + piață)

În tab-ul **Costuri parc**, alege o strategie, un split (antrenare/validare/test) și o zi de livrare — aleatorie sau exactă, cu seed dacă vrei să repeți rularea. Simularea decontează ziua în RON: venit din distribuție, cost de primire, uzura bateriei și profitul net, plus prețul OPCOM PZU la 15 minute, PV real vs prognoză, nivelul de încărcare și puterea bateriei. **Jurnalul deciziilor** arată replanificările zilei (la fiecare patru ore); fiecare decizie angajează până la 16 intervale și vede doar prognoza, prețurile și starea bateriei disponibile atunci.

Compară **LLM (DeepSeek)** cu **MPC**, **Reguli**, **Prag de preț**, **Oracle LP** (previziune perfectă) și **Păstrează** (fără baterie): rulează aceeași zi cu două strategii și compară profitul. LLM-ul cere `DEEPSEEK_API_KEY` în `RL/.env` și poate dura câteva minute; dacă nu primește un plan valid, trece pe planul de rezervă bazat pe reguli. Celelalte strategii merg fără cheie API.

Partea de costuri are nevoie de mediul `RL/` (o singură dată: `cd RL && uv sync`; vezi `RL/README.md`). Ea se leagă de inspecție: findings-urile confirmate în pasul **Review** reduc producția PV din simulare, iar factorul de derate apare sus, în **Costuri parc**. Confirmă sau respinge un finding și rulează din nou ziua ca să vezi efectul în bani.

## Cifrele — SolarTriage (test split, `reports/eval.json`)

| Model | macro-F1 (8 clase) |
|---|---|
| Reguli pe trăsături de intensitate | 0,374 |
| Random Forest pe aceleași trăsături | 0,541 |
| **ResNet18 × 2** (ansamblu pre-antrenat, fine-tune pe Kaggle, servit cu ONNX Runtime) | **0,729** |
| CNN mic antrenat de la zero (ablație, fără pre-antrenare) | 0,588 |

- **Degradare** (macro-F1 la nivelul 1 / 2 / 3): zgomot 0,719 / 0,618 / 0,293 · blur 0,722 / 0,686 / 0,483 · contrast 0,694 / 0,548 / 0,262.

- **Modelul:** două ResNet18 antrenate pe Kaggle (label smoothing; augmentări cu reflexii și blur, alt seed), cu media pe 4 flip-uri și pe modele și un bias pe clase, totul într-un singur `model.onnx` (tichetul 36). Ales doar pe validare: macro-F1 0,719 → 0,744, automat 59,5% → 64,0%.
- **Calibrare:** temperature scaling (T = 0,76), ECE 0,106 → 0,031.
- **„Nu sunt sigur”:** pragurile sunt alese pe val pentru precizie ≥ 95% pe ce trece automat. Pe test trec automat 64,5% dintre crop-uri, la precizie 95,7%. Restul merg la inginer și primesc ordin „verifică și repară”, în afară de cele la care modelul dă cel puțin 10% șanse că modulul e sănătos: acestea stau „de urmărit”, fără ordin, până le confirmă inginerul.
- **Decizia** (ADR 0001): scorul = risc așteptat Σ p(c) × pondere × kWh/zi pierduți; ΔT ≥ 20 K → critical + alertă pe orice clasă. Regulile sunt în `backend/config/decision_rules.yaml`, editabile de un inginer.

Toate cifrele din `reports/eval.json` se regenerează cu `uv run --project backend python evaluate.py`, pe datele de test, care nu au fost folosite la antrenare sau la alegerea pragurilor. Prima rulare a evaluării instalează și mediul `ml/` (torch CPU, câteva minute); pe Windows, setează înainte `$env:PYTHONUTF8=1`.

## Teste

Fiecare parte are suita ei:

```bash
cd backend && uv run pytest -q && uv run ruff check .
```

```bash
cd frontend && npm run lint && npm run build && npm run e2e
```

```bash
cd ml && uv run pytest -q
```

```bash
cd RL && uv sync --extra dev && uv run pytest -q && uv run ruff check .
```

- **backend** — simulatorul, pipeline-ul, cele 6 cazuri de robustețe, decizia, planner-ul, contractele, evaluarea și regula de 30 KB pe fișier sursă. Are nevoie de crop-urile Raptor (pasul de date de mai sus); fără ele, testele care le folosesc eșuează.
- **frontend** — oxlint, build TypeScript/Vite și Playwright pe cele 3 scenarii. Playwright își pornește singur serverele pe :8100 și :5180; prima dată instalează browserul cu `npx playwright install chromium`.
- **ml** — antrenarea și exportul ONNX, calibrarea, TTA + bias-ul pe clase și indexul de cazuri similare; testele care au nevoie de crop-uri se sar dacă lipsește `data/raptor/`.
- **dispatch** (pachetul `RL/`) — configul, contractele de date, mediul, strategiile și agentul LLM, plus ruff.

`make lint` rulează `ruff check` + `ruff format --check` pe backend și oxlint pe frontend. `make test` rulează doar backend + build frontend, nu suitele `ml`/dispatch/e2e.

## Structura

```
backend/app/services/   sim/ (parc, compunere, artefacte) · pipeline/ (check, register, consistency, infer, calibrate, analyse)
                        decision/ (reguli, pierdere, ordine, planner, alerte) · explain/ (Grad-CAM, cazuri similare) · report/
backend/config/         decision_rules.yaml · loss.yaml · pvgis_bucharest.json · weather.json · crews.yaml
backend/artifacts/      model.onnx · temperature.json · thresholds.json · best.pt (Grad-CAM) · embeddings.npy (similare)
frontend/src/           components/ (ParkMap, DronePlayer, FindingCard, PlanView, ...) · api/types.gen.ts (din OpenAPI)
ml/                     fetch_raptor.py · data.py · train.py · calibrate.py · export_onnx.py · notebooks/train_kaggle.ipynb · splits/*.csv
RL/                     pachet separat: prognoză PV · dispecerizare baterie · evaluarea strategiilor
data/raptor/            crop-urile Raptor descărcate (gitignored)
evaluate.py             cifrele de mai sus → reports/eval.json
docs/                   DESIGN_SPEC.md · adr/
```

## Date, antrenare și licență — SolarTriage

Toate modelele și pragurile se obțin din același set de date, împărțit o singură dată de `ml/data.py` (70/15/15, stratificat pe cele 8 clase, seed fix; un grup de aproape-duplicate nu traversează split-urile):

| Split | Crop-uri | Folosit pentru |
|---|---|---|
| `ml/splits/train.csv` | 13.972 | ResNet18, CNN-ul mic (ablație), Random Forest, pragurile regulilor |
| `ml/splits/val.csv` | 2.995 | selectarea modelului pe macro-F1, calibrarea (T), pragurile „unsure” |
| `ml/splits/test.csv` | 2.977 | o singură rulare de evaluare (`evaluate.py`) și cadrele demo din simulator |

**Sursa:** [InfraredSolarModules](https://github.com/RaptorMaps/InfraredSolarModules) (Raptor Maps, licență MIT) — 20.000 de crop-uri termice de 24×40 px, 12 clase Raptor mapate de noi pe 8, publicat la ICLR 2020, workshop-ul AI for Earth Sciences ([lucrarea](https://ai4earthscience.github.io/iclr-2020-workshop/papers/ai4earth22.pdf)). După eliminarea duplicatelor rămân 19.944. `ml/fetch_raptor.py` descarcă arhiva oficială de pe GitHub și o verifică cu SHA-256; datele nu intră în repo, split-urile da.

**Rețele:** ResNet18 pornește din greutățile ImageNet (`ResNet18_Weights.IMAGENET1K_V1` din torchvision) și e fine-tuned pe split-ul train, în notebook-ul Kaggle; CNN-ul mic e antrenat de la zero pe același split. Nu folosim date externe, date de client sau imagini din altă sursă.


## Partea de dispatch a bateriei

Repo-ul găzduiește și optimizarea costurilor fermei (baterie + piață), în pachetul separat `RL/` cu propriul mediu și README: `RL/README.md`. Backend-ul o cheamă prin `RL/.venv`, deci instaleaz-o o dată cu `cd RL && uv sync` înainte de tab-ul **Costuri parc**.

**Datele părții de dispatch:** prețuri OPCOM PZU la 15 minute, cerere națională ENTSO-E, PV realizat din arhiva de radiație Open-Meteo (proxy, nu contor), iar prognoza PV (`hgb-pv-v1`) din prognoze ECMWF IFS prin Open-Meteo Single Runs plus aerosol din arhiva de calitate a aerului. Detalii în `RL/PV_MODEL.md` și `RL/artifacts/data/processed/data_card.md`. Agentul LLM folosește DeepSeek API (`DEEPSEEK_API_KEY` în `RL/.env`).

Setup-ul comun de backend + frontend e prin `make setup` / `make dev`; pe Windows, `setup.ps1` / `dev.ps1`. Ambele creează și `RL/.env`, dar nu instalează mediul de dispatch. Docker (`make up`) pornește doar backend + frontend; partea de costuri nu e inclusă în container.
