# SolarTriage — Design spec (Smarthack XI, tema PPC „24h to Power PPC”)

> **Stack fix:** backend **Python + FastAPI**, frontend **React (Vite)**. Comunicare HTTP/JSON + SSE prin FastAPI.
> Orice secțiune de mai jos se referă la acest stack; nu există alternative.
> **Regula de cod:** niciun fișier sursă peste **30 KB** (vezi §11). Puțin cod, dar corect.

---

## 1. Problemă, utilizator, destinație

- **Problema:** inspecția cu drona produce sute de anomalii; transformarea lor în ordine de lucru e manuală, lentă (săptămâni) și inconsistentă.
- **Utilizator:** inginerul O&M al unui operator de portofoliu (PPC Renewables). Decide zilnic ce se repară, de cine, când.
- **Destinația la H24:** agent cap-coadă în FastAPI (cadru → data check → înregistrare → model → calibrare → decizie → acțiuni), UI de demo în React, model antrenat de noi și evaluat pe test separat față de 2 baseline-uri, `evaluate.py` care regenerează toate cifrele, repo public cu commit-uri în cele 24h.

## 2. Arhitectură

```
┌──────────────── React (Vite) ────────────────┐        ┌──────────────────── FastAPI (Python) ────────────────────┐
│ ParkMap · DronePlayer · FrameStrip           │  HTTP  │ api/        routere                                       │
│ FindingCard · ReviewQueue · PlanView         │ ─────► │ sim/        parc + cadre compuse din crop-uri Raptor      │
│ AlertBanner · TicketInbox · AgentTimeline    │  JSON  │ pipeline/   check → register → consistency → infer        │
│ ReportView · EvalView                        │ ◄───── │ decision/   reguli YAML, pierdere, planner, work orders   │
│ Zustand store ◄── useMissionStream (SSE)     │  SSE   │ explain/    Grad-CAM, cazuri similare                     │
└──────────────────────────────────────────────┘        │ store.py    SQLite (SQLModel) + stare în memorie          │
                                                        │ report/     template Jinja2 → HTML                        │
   ml/ (offline, Kaggle GPU) ──► backend/artifacts/     └───────────────────────────────────────────────────────────┘
   model.onnx · temperature.json · thresholds.json · embeddings.npy
```

- **FastAPI** e singura sursă de adevăr: generează cadrele, rulează modelul (ONNX Runtime, încărcat o dată la startup), decide și execută acțiunile.
- **React** ține doar starea de UI și afișează ce vine din FastAPI. Nu există inferență în browser.
- **LLM:** nu se folosește implicit. Raportul vine din template. Un LLM pentru rezumat se adaugă doar după H18, dacă rămâne timp.

## 3. Date și ML (P1)

### 3.1 Date
- **Set principal:** InfraredSolarModules (Raptor Maps), 20.000 de crop-uri IR de 24×40, 12 clase, descărcat de `ml/data.py` de pe GitHub-ul oficial. Datele nu intră în repo.
- **Deduplicare** cu hash perceptual înainte de split, ca aproape-duplicatele să nu ajungă și în train, și în test.
- **Split** stratificat 70/15/15, seed fix. `ml/splits/{train,val,test}.csv` **intră în repo**.
- **Fără RGB Kaggle și fără alte seturi.** Datele sintetice servesc doar pentru robustețe (§6).

### 3.2 Maparea pe 8 clase
| Raptor (12) | SolarTriage (8) |
|---|---|
| Cell, Hot-Spot | `hot_cell` |
| Cell-Multi, Hot-Spot-Multi | `multi_hot` |
| Diode, Diode-Multi | `diode_substring` |
| Offline-Module | `module_offline` |
| Soiling | `soiling` |
| Shadowing, Vegetation | `shadow_vegetation` |
| Cracking | `other` |
| No-Anomaly | `ok` |

Glare-ul **nu** e clasă. E tratat de pipeline (§5, consistency check).

### 3.3 Modele comparate
1. **Baseline A, reguli:** `classify()` din PoC, portat pe trăsături de intensitate (vârf față de mediană, aria fierbinte, număr de pete, bandă pe 1/3, modul uniform) și **extins la toate 8 clasele**. Pragurile se ajustează pe train.
2. **Baseline B:** Random Forest pe aceleași trăsături.
3. **Model principal:** ResNet18 pre-antrenat pe ImageNet. Crop-ul gri se replică pe 3 canale, input 64×96. Class weights + oversampling ușor. Augmentări: flip H/V, ±luminozitate, zgomot, fără rotație de 90°. Selecție pe macro-F1 pe val.
4. *(Opțional, primul tăiat)* un CNN mic de la zero, ca ablație.

Export: `model.onnx`, servit din FastAPI cu ONNX Runtime. Grad-CAM se calculează cu PyTorch pe CPU, la cerere.

### 3.4 Calibrare și „nu sunt sigur”
- Temperature scaling pe val (un parametru T), cu ECE și reliability diagram înainte/după.
- Pragurile de incertitudine se aleg pe val după o țintă: **precizie ≥ 95% pe ce trece automat**. Valorile 0,6 și 0,15 sunt doar punct de pornire.
- Praguri **pe grup de severitate**, în `thresholds.json`. Clasele cu risc (`hot_cell`, `multi_hot`, `diode_substring`) au pragul mai strict. Un `ok` cu probabilitate mare pe o clasă de risc merge tot în coadă.

### 3.5 Explicabilitate (în FastAPI, afișată în React)
1. ΔT aparent + pattern (din trăsăturile baseline-ului).
2. Grad-CAM pe crop: `GET /findings/{id}/gradcam.png`, cu cache pe disc.
3. Trei cazuri similare: embedding-uri 512-d din stratul penultim, pe tot train set-ul (`embeddings.npy`), căutare cosine cu numpy.
4. Regula de decizie aplicată, citată din YAML.

### 3.6 Plan de evaluare (`evaluate.py`)
Rulează pe **test**, o singură dată, cu `backend/artifacts/model.onnx`. Scrie `reports/eval.json` și figurile:
- macro-F1 pe 8 și pe 12 clase, plus F1 per clasă, pentru reguli → RF → ResNet18
- matricea de confuzie (8 clase)
- ECE și reliability diagram, înainte/după calibrare
- curba risk–coverage cu pragul ales
- testul de degradare: zgomot, blur și contrast, pe 3 niveluri, cu macro-F1 per nivel
- analiza erorilor: top confuzii cu 6 exemple fiecare
- cifrele de robustețe pe pipeline (§6)

Tab-ul `EvalView` din React citește același `eval.json`.

## 4. Simulatorul (în FastAPI, `backend/sim/`)

Simulatorul HTML/JS vanilla e portat. Logica se mută în FastAPI, iar desenul în React.

- **Layout:** 2 blocuri × 5 rânduri × 4 mese × 12 module = **480 de module**. O masă are 2×6 module în portret. String = 2 mese (24 de module), deci 2 string-uri pe rând. Un invertor pe rând, adică 10 invertoare × 48 de module. ID-uri `B1-R2-T3-M07`, string `B1-R2-S2`, invertor `INV-1.2`. Rândurile sunt la 9 m, blocurile la 45 m.
- **Geometrie:** modul de 6×10 celule × 4 px = **24×40**, exact cât un crop Raptor. Cadrul acoperă o masă.
- **Compunere:** fiecare slot primește un **crop Raptor din test split**, din clasa defectului plantat (No-Anomaly pentru modulele sănătoase). Conversia în temperatură aparentă: `T = T_bază + (pix − median_ok) × k`, cu `k = 0,15 K/nivel` (documentat). `T_bază` scade sub nor. Adevărul de teren e cunoscut.
- **Două treceri pe masă** (`pass_no` 1 și 2), din poziții puțin diferite. Glare-ul apare într-o singură trecere, defectul în ambele.
- **Artefacte și injectări:** nor (iradianță 420–480), glare (2×2 celule, +7…11 K, o trecere), decalaj GPS (±1 modul, slot-ul liber arată **sol la 28 °C**), cadru pierdut, RGB din greșeală (3 canale, `radiometric=false`), cadru fără panouri, iradianță < 600.
- **Determinism:** totul depinde de `seed`. Cadrele nu se salvează, se regenerează. Misiunile demo au seed fix.

## 5. Pipeline-ul (FastAPI, `backend/app/pipeline/`)

| Pas | Fișier | Ieșire |
|---|---|---|
| 1. Data check | `check.py` | respinge: iradianță < 600, vânt > 8, fără timp/poziție, temperaturi invalide, `channels≠1` sau `radiometric=false` (RGB), nicio grilă de module găsită (fără panouri). Masă respinsă → `not_inspected` + propunere de re-zbor. |
| 2. Înregistrare | `register.py` | caută coloana de sol sau marginea mesei, calculează offset-ul în module și re-alocă slot-urile. Modulul fără imagine → `not_inspected`. |
| 3. Inferență | `infer.py` | crop 24×40 → ONNX → logits → softmax(z/T) |
| 4. Consistență | `consistency.py` | anomalie doar într-o trecere → „reflexie probabilă”, urgență scăzută, coadă. O trecere lipsă → se folosește cealaltă. |
| 5. Incertitudine | `calibrate.py` | `unsure` + motiv, după `thresholds.json` |
| 6. Decizie | `decision/` | urgență, pierdere, echipă, piesă, scor (§7) |
| 7. Acțiuni | `decision/` + `api/` | ordine de lucru, alerte, webhook, plan, jurnal (§8) |

Status per modul: `pending | ok | finding | unsure | not_inspected`. Un modul fără date valide nu e niciodată „ok”.

Baseline-ul rulează în paralel pe fiecare crop (`baseline_cls` în `Finding`), ca ecranul de rezultate să arate model vs. reguli vs. adevăr.

## 6. Suita de robustețe (FastAPI + `pytest`, injectabilă din React)

| Caz | Comportament | Cifra din `evaluate.py` |
|---|---|---|
| Cadru lipsă | masa `not_inspected` sau fallback pe cealaltă trecere, re-zbor propus | % module acoperite cu 1 / 2 cadre lipsă |
| Iradianță < 600 | cadru respins cu motiv, re-zbor | 0 finding-uri pe cadre sub prag |
| RGB din greșeală | respins de data check | 100% respinse din N |
| Fără panouri | respins (nicio grilă) | 100% respinse |
| Glare | reflexie probabilă → coadă | alarme false din glare, înainte/după |
| Decalaj GPS | offset detectat și corectat | ratate + alarme false, înainte/după |

Toate 6 sunt teste în `backend/tests/test_robustness.py`.

## 7. Stratul de decizie (FastAPI, `backend/config/decision_rules.yaml`)

Reguli explicite, editabile de un inginer. Fără un al doilea model.

1. **Siguranță:** `hot_cell` / `multi_hot` / `diode_substring` cu ΔT aparent ≥ **20 K** → urgență `critical` + alertă imediată.
2. **Urgență de bază:** `module_offline`, `diode_substring` → high. `hot_cell`, `multi_hot` → medium. `shadow_vegetation`, `soiling`, `other` → low.
3. **Scor:** `pondere_urgență × pierdere_kWh/zi`. La egalitate câștigă încrederea. Finding-urile `unsure` nu intră în plan până nu le confirmă inginerul.

Per clasă, în YAML: echipă (`electrical` / `cleaning`), piesă probabilă, durată (diodă 1,5 h, modul 2 h, conectori 0,5 h, curățare 0,25 h), verificare sugerată.

**Pierderea (`loss.yaml`):** `kWh/zi = 0,55 kWp × fracție × yield_zilnic`, cu yield-ul din `pvgis_bucharest.json` (lunar, offline, ~1.350 kWh/kWp/an). Fracții: offline 1,00 · diode 0,33 · multi_hot 0,10 · shadow 0,10 · soiling 0,08 · hot_cell 0,03 · other 0,05. RON/zi la un preț fix din config. ΔT nu intră în pierdere.

**Planner (`planner.py`, greedy):** 2 echipe, 7 h/zi fiecare. Deplasare 10 min între rânduri, 20 min între blocuri. Meteo din `weather.json` pe 5 zile: electricienii nu lucrează pe ploaie, curățenia nu lucrează pe vânt > 10 m/s. Pașii: alertele critice în ziua 1 → sortare după scor → sarcinile din aceeași masă/rând și aceeași echipă trase împreună → umplere până la capacitate → restul în următoarea zi cu vreme bună. **Fiecare sarcină are un `reason` scris.**

**Feedback:** confirm / reject / inconclusive se scrie în SQLite și reface imediat ordinele de lucru și planul (inconclusive → reinspecție). Acordul om–model per clasă apare în raport. `GET /missions/{id}/labels.csv` exportă etichetele. Pragurile și modelul **nu** se ajustează live.

## 8. Acțiuni (FastAPI, afișate în React)

- **Lista de priorități:** finding-urile sortate după scor.
- **Ordine de lucru:** JSON sau CSV, cu modul, string, invertor, tip, piesă, echipă, durată, urgență și dovadă (URL de crop/cadru, timestamp).
- **Webhook:** un `POST` per ordin sau alertă către `WEBHOOK_URL` din config. Implicit e `/mock/ticketing` din același FastAPI. Dovezile merg ca URL-uri, nu ca imagini. 3 reîncercări, totul logat.
- **Alertă critică:** webhook + eveniment SSE `alert_raised` → `AlertBanner`, cu confirmare de primire.
- **Coada „nu sunt sigur”:** `ReviewQueue`.
- **Jurnalul agentului:** `AgentEvent` pentru fiecare cadru respins, re-zbor, ordin, alertă și replanificare, fiecare cu motiv → `AgentTimeline`.
- **Raport:** HTML din Jinja2 (`GET /missions/{id}/report`), fără PDF.

## 9. Contracte API (FastAPI + Pydantic → tipuri TypeScript pentru React)

`backend/app/schemas.py`. React generează `types.gen.ts` din `/openapi.json` cu `openapi-typescript`. Până la H6, FastAPI servește mock-uri cu forma finală.

```python
FaultClass = Literal["ok","hot_cell","multi_hot","diode_substring","module_offline",
                     "soiling","shadow_vegetation","other"]
Urgency = Literal["critical","high","medium","low"]
ModuleStatus = Literal["pending","ok","finding","unsure","not_inspected"]

class Module(BaseModel):
    id: str; table: str; string: str; inverter: str
    block: int; row: int; pos: int; x_m: float; y_m: float

class MissionSettings(BaseModel):
    seed: int = 7; n_faults: int = 12
    p_cloud: float = .10; p_gps: float = .06; p_glare: float = .10; p_lost: float = .03
    inject: list[Literal["rgb","no_panels","low_irr","missing"]] = []
    speed: float = 1.0

class Mission(BaseModel):
    id: str; settings: MissionSettings
    phase: Literal["planned","flying","checked","analysed","reviewed","done"]
    modules: list[Module]; status: dict[str, ModuleStatus]
    truth: dict[str, FaultClass] | None = None        # doar în modul demo

class FrameMeta(BaseModel):
    id: str; table: str; pass_no: Literal[1, 2]; file: str; timestamp: str
    lat: float; lon: float; irradiance_wm2: float; wind_ms: float
    channels: int; radiometric: bool
    check_ok: bool; problems: list[str]
    gps_offset_detected: int                          # module; 0 = aliniat
    thumb_url: str

class Prediction(BaseModel):
    cls: FaultClass; probs: dict[FaultClass, float]; temperature: float
    unsure: bool; unsure_reason: str | None = None

class SimilarCase(BaseModel):
    id: str; cls: FaultClass; crop_url: str; distance: float

class Evidence(BaseModel):
    frame_ids: list[str]; crop_url: str; gradcam_url: str | None = None
    delta_t_k: float; pattern: str; seen_in_both_passes: bool
    similar: list[SimilarCase] = []; rule_applied: str

class Finding(BaseModel):
    id: str; module_id: str; prediction: Prediction; baseline_cls: FaultClass
    urgency: Urgency; loss_kwh_day: float; loss_ron_day: float; score: float
    crew: Literal["electrical","cleaning"]; part: str | None; est_hours: float
    evidence: Evidence
    review: Literal["confirmed","rejected","inconclusive"] | None = None
    review_note: str | None = None

class ReviewIn(BaseModel):
    decision: Literal["confirmed","rejected","inconclusive"]; note: str | None = None

class WorkOrder(BaseModel):
    id: str; finding_id: str; module_id: str; string: str; inverter: str
    fault: FaultClass; part: str | None; crew: str; est_hours: float
    urgency: Urgency; evidence_url: str; created_at: str; ticket_status: str

class PlanTask(BaseModel):
    work_order_id: str; crew: str; start_h: float; duration_h: float; reason: str

class PlanDay(BaseModel):
    day: int; date: str; weather: str; capacity_h: dict[str, float]
    used_h: dict[str, float]; tasks: list[PlanTask]

class Plan(BaseModel):
    days: list[PlanDay]; unscheduled: list[str]; total_loss_avoided_kwh: float

class Alert(BaseModel):
    id: str; finding_id: str; level: Literal["critical"]; message: str
    raised_at: str; acknowledged: bool = False

class AgentEvent(BaseModel):
    ts: str; kind: str; message: str; ref: str | None = None

class StreamEvent(BaseModel):                         # SSE
    type: Literal["waypoint","frame_captured","frame_checked","cloud","flight_done",
                  "findings_ready","alert_raised","agent_event"]
    data: dict
```

| Metodă | Endpoint FastAPI | Folosit în React de |
|---|---|---|
| GET | `/park` | `ParkMap` |
| POST | `/missions` · `/missions/demo/{scenario}` | `PhasePanel` |
| GET | `/missions/{id}` (resincronizare) · `/missions/{id}/stream` (SSE) | store |
| POST | `/missions/{id}/fly` · `/missions/{id}/refly` · `/missions/{id}/analyse` | `PhasePanel` |
| GET | `/missions/{id}/frames` · `/frames/{id}/thumb.png` | `FrameStrip` |
| GET | `/missions/{id}/findings` | `PriorityList`, `ReviewQueue` |
| POST | `/findings/{id}/review` (`ReviewIn`) | `FindingCard` |
| GET | `/findings/{id}/crop.png` · `/findings/{id}/gradcam.png` | `FindingCard` |
| GET | `/missions/{id}/work-orders?format=json\|csv` · `/missions/{id}/labels.csv` | `PriorityList` |
| GET | `/missions/{id}/plan` | `PlanView` |
| GET/POST | `/missions/{id}/alerts` · `/alerts/{id}/ack` | `AlertBanner` |
| GET | `/missions/{id}/events` | `AgentTimeline` |
| GET | `/missions/{id}/report` · `/missions/{id}/score` | `ReportView`, ecranul de adevăr |
| POST | `/analyse` (un crop → `Prediction`) | `evaluate.py`, teste |
| GET/POST | `/mock/ticketing` | `TicketInbox` |
| GET | `/eval` (servește `reports/eval.json`) | `EvalView` |

## 10. Frontend React (Vite, `frontend/`)

- **Un ecran principal** cu bara de faze 1–8 (din simulator). Stânga: `ParkMap` + `FrameStrip`. Dreapta: `PhasePanel` / `FindingCard`. Tab-uri: Plan, Raport, Evaluare.
- **Componente:** `ParkMap` (un `<canvas>`, desen portat din `draw()`, straturi: status, adevăr, outcome, dronă, amprentă), `DronePlayer` (doar interpolare, fără desen), `FrameStrip`, `PhasePanel`, `FindingCard`, `ReviewQueue`, `PriorityList`, `PlanView`, `AlertBanner`, `TicketInbox`, `AgentTimeline`, `ReportView` (iframe pe HTML-ul din FastAPI), `EvalView` (Recharts).
- **Stare:** Zustand (`missionStore.ts`) pentru tot ce vine din FastAPI. SSE scrie **doar** din `useMissionStream.ts`. `useState` local pentru UI (selecție, tab, overlay adevăr). Fără Redux sau React Query. Un singur `api.ts` cu fetch-uri tipizate.
- **Animația dronei:** FastAPI trimite `waypoint` (poziția țintă) cu un `sleep` dat de `speed`. React interpolează cu `requestAnimationFrame`. Dacă SSE cade, un singur fetch pe `GET /missions/{id}` resincronizează.
- **Stil:** Tailwind v4 (deja în template), cu culorile simulatorului. Tab-urile folosesc `react-router-dom` (deja în template), cu `pages/` pentru Main, Plan, Report și Eval. Fără design system și fără autentificare.

## 11. Structura repo-ului și regula de 30 KB

Structura extinde template-ul din repo (`S-WAGG`), fără să-l rescrie. Toate rutele FastAPI sunt montate sub **`/api`** (deja în `main.py`), iar Vite face proxy la `/api` spre `:8000`. Endpoint-urile din §9 sunt deci `/api/park`, `/api/missions` și așa mai departe, iar OpenAPI e la `/api/openapi.json`.

```
S-WAGG/
├─ backend/                         # FastAPI (template)
│  ├─ app/
│  │  ├─ main.py                    # + încărcarea modelului ONNX în lifespan
│  │  ├─ api/router.py              # include routerele de mai jos
│  │  ├─ api/routes/                # health.py · park.py · missions.py · findings.py · actions.py · mock.py · eval.py
│  │  ├─ core/                      # config.py (+ WEBHOOK_URL, căi model/config) · db.py (SQLite)
│  │  ├─ models/                    # tabele SQLModel: mission, finding, review, work_order, alert, agent_event
│  │  ├─ schemas/                   # Pydantic din §9: park.py · mission.py · finding.py · actions.py · stream.py
│  │  └─ services/
│  │     ├─ sim/                    # park.py · compose.py · artefacts.py
│  │     ├─ pipeline/               # check.py · register.py · consistency.py · infer.py · calibrate.py
│  │     ├─ decision/               # rules.py · loss.py · planner.py · workorders.py · alerts.py
│  │     ├─ explain/                # gradcam.py · similar.py
│  │     ├─ baseline/               # features.py · rules_classifier.py
│  │     ├─ state.py                # starea misiunii în memorie
│  │     └─ report/report.html.j2
│  ├─ config/                       # decision_rules.yaml · loss.yaml · pvgis_bucharest.json · weather.json
│  ├─ artifacts/                    # model.onnx · temperature.json · thresholds.json · embeddings.npy
│  └─ tests/                        # test_health.py · test_robustness.py · test_contracts.py · test_file_size.py
├─ frontend/                        # React (Vite, template)
│  └─ src/
│     ├─ api/                       # client.ts (template) · types.gen.ts (din OpenAPI)
│     ├─ store/                     # missionStore.ts (Zustand) · useMissionStream.ts
│     ├─ components/                # Layout (template) · ParkMap · DronePlayer · FrameStrip · ...
│     └─ pages/                     # Main · Plan · Report · Eval (+ Home/NotFound din template)
├─ ml/                              # data.py · features.py · train.py · calibrate.py · export_onnx.py
│                                   # build_index.py · notebooks/train_kaggle.ipynb · splits/*.csv
├─ evaluate.py
├─ docs/DESIGN_SPEC.md
└─ README.md · setup.ps1 · dev.ps1 · Makefile (template)
```

Artefactele modelului stau în `backend/artifacts/`, nu în `backend/app/models/`, pentru că acolo template-ul ține tabelele SQLModel.

**Regula de 30 KB pe fișier:**
- Niciun fișier sursă (`.py`, `.ts`, `.tsx`, `.css`, `.j2`, `.yaml`) nu trece de **30.720 bytes** (~600–700 de linii). Când un fișier se apropie de limită, se sparge pe responsabilități, nu se comprimă codul.
- Excepții: artefacte generate și binare (`types.gen.ts`, `model.onnx`, `*.npy`, lockfile-uri, `splits/*.csv`, notebook-uri).
- Verificarea e automată în `backend/tests/test_file_size.py`, care parcurge repo-ul și pică dacă un fișier depășește limita. Rulează odată cu `pytest`, înainte de fiecare merge în `main`.
- Spiritul regulii: cea mai simplă variantă corectă. Fără abstracții „pentru viitor”, fără cod duplicat între FastAPI și React (logica stă doar în FastAPI).

**Cele 3 comenzi din README** (pe Windows există și `setup.ps1` / `dev.ps1` din template):
```bash
cd backend && uv sync && uv run fastapi dev app/main.py
```
```bash
cd frontend && npm install && npm run dev
```
```bash
uv run --project backend python evaluate.py
```

`model.onnx` (~45 MB) intră în repo. Juriul nu antrenează nimic.

## 12. Scenariile de demo (sub 7 minute, seed fix: `POST /missions/demo/{scenario}`)

1. **Ziua normală, ~3 min (agent + ML):** zbor → 14 finding-uri → hot cell cu ΔT 22 K → alertă critică (banner + tichet în Inbox) → priorități → plan pe 3 zile cu o zi de ploaie → CSV. Mesajul: „de la zbor la ordine de lucru în 40 s, nu în săptămâni”.
2. **Ziua proastă, ~2 min (robustețe):** nor, cadru lipsă, RGB, fără panouri, glare, GPS → mese hașurate cu motiv, re-zbor propus, glare prins pe două treceri, GPS corectat (înainte/după).
3. **De ce are dreptate, ~1,5 min (explicabilitate + ML):** finding de diodă cu Grad-CAM, ΔT, cazuri similare și regulă → un caz `unsure`, confirmat → planul se reface live → tab-ul Evaluare (reguli → RF → ResNet18, confuzie, calibrare, degradare).
4. **30 s:** repo-ul, cele 3 comenzi, `evaluate.py`.

**Plasă de siguranță:** video cu toate trei, înregistrat la H22.

## 13. Oameni și ore

| Ore | P1 · ML | P2 · Backend FastAPI | P3 · Frontend React | P4 · Date/produs/integrare |
|---|---|---|---|---|
| 0–2 | download, dedup, split, mapare | contracte, schelet, mock-uri | contracte, Vite, tipuri generate | conduce contractele |
| 2–6 | trăsături, reguli, RF; ResNet18 v0 → **ONNX la H6** | pipeline: check, register, consistency (2–5); ONNX + `/analyse` (5–7) | `ParkMap`, `DronePlayer` pe mock-uri | `sim/`: layout, compunere Raptor, 2 treceri, toate injectările |
| 6–10 | antrenare completă | YAML, pierdere, ordine de lucru (7–9); SSE, SQLite, review (9–11) | `FrameStrip`, `PhasePanel`, SSE → **cap-coadă la H8**; `FindingCard`, `ReviewQueue`, `PriorityList` (8–11) | conținut YAML, pierderi, PVGIS/meteo (6–8); seed-uri demo, README (8–10) |
| 10–14 | calibrare, praguri (10–12); Grad-CAM, embeddings (12–15) | alerte, webhook mock, jurnal (11–13); **somn 13–16** | **somn 11–14** | template raport (10–12); al doilea om pe frontend (12–17) |
| 14–18 | `evaluate.py`, degradare, erori (15–18) | planner (16–18) | `PlanView`, `AlertBanner`, `TicketInbox`, `AgentTimeline` (14–17); `EvalView`, `ReportView` (17–20) | **somn 17–20** |
| 18–24 | **somn 18–20**; figuri, buffer | `pytest` robustețe (18–20); integrare | finisaj, demo | slide-uri (20–22), video H22, repetiție H23 |

**Puncte de control:**
- H2: contracte fixate
- H6: model v0 în FastAPI
- H8: React cap-coadă pe baseline
- H16: backend complet
- **H20: code freeze** pe funcții noi
- H22: video
- H23: repetiție

Perechile P1/P2 și P3/P4 nu dorm niciodată simultan. Câte o ramură pe persoană, merge în `main` la fiecare punct de control, commit-uri mici și dese.

## 14. Ordinea de tăiere (decide P4)

1. LLM pe rezumat
2. CNN-ul mic de ablație
3. Testul de degradare
4. Cazurile similare
5. Meteo din plan
6. `TicketInbox` în React
7. Grad-CAM
8. Consistency check pe două treceri

Regulă automată: dacă H8 e ratat cu peste o oră, se taie 1–3. Dacă H16 e ratat, se taie 4–5.

**Nu se taie niciodată:** modelul + testul separat + baseline-urile + matricea de confuzie, pipeline-ul cap-coadă în FastAPI, ordinele de lucru și alerta, coada „nu sunt sigur”, data check-ul cu `not_inspected`, `evaluate.py`, cele 3 comenzi, regula de 30 KB.

## 15. În afara scopului

Zbor real, ortomozaic, YOLO / detecție de panouri, clasificator RGB și fuziune, ServiceNow, ajustare live a pragurilor sau retrain în demo, PDF, interfață pentru clienți, eoliene, orice backend în afară de FastAPI și orice frontend în afară de React.

## 16. Jurnalul deciziilor (grilling)

| # | Decizie |
|---|---|
| Q1 | Cadrele demo compuse din crop-uri Raptor reale din test, slot 24×40 |
| Q2 | Mapare 12→8, macro-F1 pe 8 și 12, glare nu e clasă |
| Q3 | Baseline: reguli extinse la 8 clase + RF |
| Q4 | ResNet18, dedup + split 70/15/15, test atins o dată, ONNX |
| Q5 | Temperature scaling, praguri pe val după precizie țintă, diferențiate pe severitate |
| Q6 | Fără YOLO; decalaj GPS vizibil (sol) + pas de înregistrare |
| Q7 | Două treceri pe masă; glare prin consistency check |
| Q8 | Fără clasificator RGB; RGB respins de data check |
| Q9 | Pierdere = tabel per clasă × yield PVGIS offline |
| Q10 | Decizie: siguranță (ΔT ≥ 20 K) → urgență per clasă → scor urgență × pierdere |
| Q11 | Planner greedy, 2 echipe, grupare pe mese, meteo offline, motiv per sarcină |
| Q12 | Feedback: log + replanificare imediată + export etichete, fără ajustări live |
| Q13 | Raport din template Jinja2, LLM doar opțional după H18, fără PDF |
| Q14 | Explicație: ΔT + pattern, Grad-CAM, 3 similare, regula aplicată |
| Q15 | 6 cazuri de robustețe + degradare + `pytest` |
| Q16 | SSE pentru progres, interpolare în React, resincronizare prin GET |
| Q17 | Memorie pentru cadre și progres, SQLite pentru decizii și rezultate, seed fix |
| Q18 | Acțiuni: ordine de lucru, webhook spre mock, alerte SSE, jurnal |
| Q19 | Pydantic ca mai sus, tipuri TypeScript generate, mock-uri până la H6 |
| Q20 | React: un ecran pe faze, Zustand, un singur hook SSE |
| Q21 | 3 scenarii de demo + video de rezervă |
| Q22 | Împărțirea pe oameni și ore din §13 |
| Q23 | Ordinea de tăiere din §14 |
| Q24 | Structura repo-ului din §11, modelul în repo, datele descărcate de script |
| Q25 | Niciun fișier sursă peste 30 KB, verificat de `test_file_size.py` |
