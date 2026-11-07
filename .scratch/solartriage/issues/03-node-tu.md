# Instalează Node 22+ pe laptopul tău

Type: task
Status: open
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
