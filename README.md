# SolarTriage

> De la zborul dronei la ordine de lucru în 40 de secunde, nu în săptămâni.

O dronă termică zboară peste un parc fotovoltaic. SolarTriage verifică fiecare cadru, găsește modulele defecte cu un model antrenat de noi, spune cât de sigur e și cât pierde fiecare defect. Apoi scrie ordinele de lucru și planul pe 5 zile pentru echipe, cu meteo. Inginerul O&M doar confirmă sau respinge.

**Stack:** backend Python + FastAPI (simulator, pipeline, model ONNX, decizie, plan), frontend React + Vite + TypeScript. Comunică prin HTTP/JSON și SSE sub `/api`.

## Cum rulezi (3 comenzi)

Ai nevoie de [uv](https://docs.astral.sh/uv/) (descarcă singur Python 3.14) și de Node 22+.

```bash
uv run --project backend python evaluate.py

make setup   # install backend/frontend deps; create backend/.env, frontend/.env and RL/.env
make dev     # backend :8000 + frontend :5173
```

The RL package is installed separately; see `RL/README.md`.

- App: http://localhost:5173
- API docs (Swagger): http://localhost:8000/api/docs

Descarcă datele Raptor (15,5 MB, verificate cu SHA-256 în `data/raptor/`). Apoi regenerează toate cifrele în `reports/eval.json`. Prima rulare instalează și mediul `ml/` (torch CPU, câteva minute). Pe Windows, setează înainte `$env:PYTHONUTF8=1`.

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

Rulează `evaluate.py` înaintea backend-ului: simulatorul compune cadrele din crop-urile Raptor. Fără ele, folosește crop-uri sintetice și scenariile demo dau alte rezultate. Modelul (`backend/artifacts/model.onnx`) e deja în repo, deci nu antrenezi nimic.

## Demo (sub 7 minute)

În tab-ul **Parc**, pasul 1 are trei butoane **Demo**. Fiecare creează misiunea cu seed fix (`POST /api/missions/demo/{scenario}`). Apoi: **Pornește zborul** → **Verificarea datelor** → **Analizează** → **Review**.

1. **Ziua normală.** Zborul durează ~40 s, cadrele apar pe bandă și harta se colorează. Analiza găsește un hot cell cu ΔT 31 K, care dă alertă critică (banner + tichet în Inbox). În **Plan** vezi prioritățile și planul pe 5 zile, pe echipe concrete (`backend/config/crews.yaml`): duminică lucrează doar echipa de gardă, luni plouă și electricienii stau acasă, joi o echipă e în concediu, iar modulele le schimbă doar echipa care știe. Fiecare sarcină are ora, oamenii și motivul scris. CSV-ul se descarcă din **Plan**, raportul HTML e în **Raport**.
2. **Ziua proastă.** Nor, cadru lipsă, cadru RGB, cadru fără panouri, reflexii, eroare GPS. Mesele fără niciun cadru valid apar hașurate, cu motivul. **Re-zbor** le reface, iar GPS-ul e corectat automat.
3. **De ce are dreptate.** Fișa unui finding de diodă arată Grad-CAM, ΔT, pattern-ul, 3 cazuri similare din setul de antrenare și regula aplicată. Un caz „nesigur” are deja ordin „verifică și repară”. Dacă îl respingi, ordinul iese din plan pe loc. Tab-ul **Evaluare** arată reguli → Random Forest → ResNet18 → CNN mic, matricea de confuzie, calibrarea și testul de degradare.

## Cifrele (test split, `reports/eval.json`)

| Model | macro-F1 (8 clase) |
|---|---|
| Reguli pe trăsături de intensitate | 0,374 |
| Random Forest pe aceleași trăsături | 0,541 |
| **ResNet18** (pre-antrenat, fine-tune pe Kaggle, servit cu ONNX Runtime) | **0,706** |
| CNN mic antrenat de la zero (ablație, fără pre-antrenare) | 0,588 |

- **Degradare** (macro-F1 la nivelul 1 / 2 / 3): zgomot 0,701 / 0,547 / 0,264 · blur 0,699 / 0,661 / 0,442 · contrast 0,687 / 0,534 / 0,249.

- **Calibrare:** temperature scaling (T = 1,36), ECE 0,048 → 0,015.
- **„Nu sunt sigur”:** pragurile sunt alese pe val pentru precizie ≥ 95% pe ce trece automat. Pe test trec automat 60,1% dintre crop-uri, la precizie 96,0%. Restul merg la inginer, dar primesc tot ordin de lucru.
- **Decizia** (ADR 0001): scorul = risc așteptat Σ p(c) × pondere × kWh/zi pierduți; ΔT ≥ 20 K → critical + alertă pe orice clasă. Regulile sunt în `backend/config/decision_rules.yaml`, editabile de un inginer.

Toate cifrele se regenerează cu `evaluate.py`, pe datele de test, care nu au fost folosite la antrenare sau la alegerea pragurilor.

## Teste

```bash
cd backend && uv run pytest -q
```

```bash
cd frontend && npm run build && npm run e2e
```

`pytest` acoperă simulatorul, pipeline-ul, cele 6 cazuri de robustețe, decizia, planner-ul și regula de 30 KB pe fișier sursă. Playwright parcurge cele 3 scenarii prin React și FastAPI; pornește singur serverele pe :8100 și :5180.

## Secrets

API keys and connection strings live in `.env` files: `backend/.env` and `RL/.env`. They are
gitignored; only the `.env.example` templates are tracked. `make setup` / `setup.ps1` copies
each template to `.env` if it does not exist. Fill in the keys you have locally and never
commit them.

Do not put secrets in `frontend/.env`: `VITE_*` values are bundled into the browser client.
`RL/scripts/check_env.py` reports which RL keys are set without printing their values.

## Structure

```
backend/
  app/
    main.py          FastAPI app, CORS, router mount (/api)
    api/router.py    register routers here
    api/routes/      one file per resource (health.py as example)
    api/deps.py      shared dependencies (SessionDep)
    core/config.py   settings from env vars / backend/.env
    core/db.py       engine + session (SQLite by default)
    models/          DB tables (SQLModel table=True)
    schemas/         request/response models
    services/        business logic, external APIs, AI calls
  tests/
frontend/
  src/
    api/client.ts    fetch wrapper -> /api (proxied to :8000 in dev)
    hooks/useApi.ts  data fetching hook
    components/      Layout + shared UI
    pages/           one file per route, register in App.tsx
    types/           TS types mirroring backend schemas
```

## Structura

```
backend/app/services/   sim/ (parc, compunere, artefacte) · pipeline/ (check, register, consistency, infer, calibrate, analyse)
                        decision/ (reguli, pierdere, ordine, planner, alerte) · explain/ (Grad-CAM, cazuri similare) · report/
backend/config/         decision_rules.yaml · loss.yaml · pvgis_bucharest.json · weather.json · crews.yaml
backend/artifacts/      model.onnx · temperature.json · thresholds.json · best.pt (Grad-CAM) · embeddings.npy (similare)
frontend/src/           components/ (ParkMap, DronePlayer, FindingCard, PlanView, ...) · api/types.gen.ts (din OpenAPI)
ml/                     data.py · train.py · calibrate.py · export_onnx.py · notebooks/train_kaggle.ipynb · splits/*.csv
evaluate.py             cifrele de mai sus → reports/eval.json
docs/                   DESIGN_SPEC.md · adr/
```

## Date și licență

Setul de date e [InfraredSolarModules](https://github.com/RaptorMaps/InfraredSolarModules) (Raptor Maps, licență MIT): 20.000 de crop-uri IR de 24×40 px, 12 clase, mapate de noi pe 8. A fost publicat la ICLR 2020, workshop-ul AI for Earth Sciences ([lucrarea](https://ai4earthscience.github.io/iclr-2020-workshop/papers/ai4earth22.pdf)). Datele nu intră în repo. `ml/data.py` le descarcă, elimină duplicatele și le împarte 70/15/15; split-urile (`ml/splits/*.csv`) sunt în repo.

## Echipa

| Cine | Rol |
|---|---|
| jiri133 | ML (date, baseline, ResNet18, calibrare, evaluare), decizie, planner |
| Alina Voronetchi | Simulator, pipeline, starea misiunii (SQLite + SSE), UI React, alerte, teste e2e |
