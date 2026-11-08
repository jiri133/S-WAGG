# Instalează Node 22+ pe laptopul tău

Type: task
Status: resolved
Owner: Tu
Țintă: H0
Blocked by: —

## Question

Fără Node nu pornește frontend-ul React și nici serverul MCP Playwright.

1. `winget install OpenJS.NodeJS.LTS`
2. Repornește aplicația Claude.
3. Verifică: `node -v` (≥ 22) și `npx -v`.

**Gata când:** `npm run dev` pornește în `frontend/`, iar serverul MCP `playwright` apare conectat.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

## Answer

Node **v26.13.0**, npm și npx 11.20.0 sunt instalate (≥ 22, ok). În `frontend/`, `npm ci` și `npm run build` trec. Serverul MCP `playwright` se verifică după repornirea aplicației Claude: în această sesiune a pornit înainte de instalarea Node și a picat atunci.

## Comments

- 2026-11-07: după repornirea Claude, serverele MCP `playwright` și `chrome-devtools` (din ECC) sunt conectate.
