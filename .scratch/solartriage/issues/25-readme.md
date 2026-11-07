# README cu cele 3 comenzi

Type: task
Status: resolved
Owner: Tu + Alina
Țintă: H21
Blocked by: 24

## Question

Spec: §11. Pitch, cele 3 comenzi, cum se rulează demo-ul și evaluarea, tabelul echipei, sursa și licența datelor.

**Gata când:** un om care clonează repo-ul pe un laptop curat ajunge la demo doar din README.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Code freeze H20: verificare cap-coadă](24-code-freeze.md)

## Answer

`README.md` rescris (în locul template-ului „Hackathon App”):
- pitch-ul;
- cele 3 comenzi, în ordinea în care merg (`evaluate.py` întâi, pentru că descarcă datele Raptor de care are nevoie simulatorul);
- cum se rulează demo-ul cu cele 3 butoane **Demo** noi din pasul Setări (`POST /api/missions/demo/{scenario}`, §12);
- cifrele din `eval.json`, testele, structura;
- sursa și licența datelor (Raptor Maps, MIT, ICLR 2020 AI for Earth Sciences);
- tabelul echipei.

**Cum am verificat (laptop curat simulat):** `git clone` al branch-ului într-un folder gol (`%TEMP%\st-clean`, fără `data/`, fără `.venv`, fără `node_modules`), apoi comenzile exact ca în README:
- `uv run --project backend python evaluate.py` → a creat mediile, a descărcat zip-ul Raptor (SHA-256 verificat) și a scris `reports/eval.json` cu aceleași cifre: reguli 0,374, RF 0,541, ResNet18 0,706, ECE 0,048 → 0,015, coverage 0,601 la 0,960. A durat 353 s.
- `cd backend && uv sync` + FastAPI (pe :8010, pentru că :8000 era ocupat de aplicația pornită din checkout-ul principal):
  - `POST /api/missions/demo/normal` → seed 22;
  - fly → `checked` în 42 s;
  - analyse în 9,2 s → 46 de findings, alerte pe hot cell-ul de 31,0 K și pe un `other` de 22,4 K;
  - plan pe 5 zile, cu ploaie în ziua 2 (0 sarcini electrice).
- `cd frontend && npm install && npm run build` → verde.
- Butoanele Demo sunt acoperite de e2e (`scenarios.spec.ts` pornește fiecare scenariu din ele): `npx playwright test` → 7 passed.
