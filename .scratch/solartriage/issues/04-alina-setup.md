# Acces GitHub și setup pe laptopul Alinei

Type: task
Status: resolved
Owner: Tu + Alina
Țintă: H0
Blocked by: —

## Question

Tu: GitHub → `jiri133/S-WAGG` → Settings → Collaborators → Add people → contul Alinei.

Alina: urmează `docs/SETUP_ALINA.md` de la cap la coadă.

**Gata când:** Alina rulează `dev.ps1`, vede aplicația pe `http://localhost:5173` și Claude din folderul repo-ului are skill-urile și pluginul ECC.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

## Answer

Setup-ul trece cap-coadă pe laptopul Alinei (Windows), verificat pe 2026-11-07 după `git pull` la `2542a79`:

- **Unelte:** git 2.56.0, Node v26.13.0, npm 12.2.2, uv 0.13.7.
- **GitHub:** repo-ul e privat, iar `git ls-remote origin` merge cu login-ul Alinei.
- **`setup.ps1`:** trece („Setup done”). Prima rulare după pull a picat la `uv sync`: uv a descărcat Python 3.14.10, apoi a dat `Missing expected target directory for Python minor version link`. A mers cu `uv sync --python <python.exe din cpython-3.14.10>`; după aceea `uv sync` simplu și `setup.ps1` trec.
- **Teste:** `cd backend && uv run pytest -q` → 32 passed; `cd frontend && npm run build` → trece.
- **Aplicația:** pornită cu aceleași comenzi ca `dev.ps1` (din `.claude/launch.json`). Swagger se deschide pe `http://localhost:8000/api/docs`; `http://localhost:5173` arată „Parcul fotovoltaic: 480 module · 2 blocuri · 10 invertoare”, cu `GET /api/park` → 200 prin proxy-ul Vite. Dacă pagina se deschide înainte să pornească backend-ul, apare „Backend-ul nu răspunde: API error 502”; un refresh rezolvă.
- **Claude:** folderul are trust; serverul MCP `playwright` e conectat și a deschis o pagină de test; pluginul ECC `ecc@ecc` 2.2.3 e instalat (scope user). Verificarea de la pasul 9, într-o sesiune nouă, trece: 71 de agenți `ecc:`, skill-urile din `.claude/skills/`, regulile din `AGENTS.md`.
- **`.gitignore`:** ignoră `.playwright-mcp/`, unde serverul MCP Playwright își salvează snapshot-urile.

## Comments

- 2026-11-07 · Tu: Alina e adăugată colaborator pe GitHub. Rămâne partea ei: docs/SETUP_ALINA.md.
