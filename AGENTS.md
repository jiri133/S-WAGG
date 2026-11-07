# AGENTS.md

## Change scope

Agents may only create, edit, move, or delete files inside these two folders:

- `frontend/`
- `backend/`

Everything else in the repository is out of scope for changes — including but not limited to
`RL/`, the repository root files (`README.md`, `Makefile`, `docker-compose.yml`, `dev.ps1`,
`setup.ps1`), `.claude/`, and any CI or tooling configuration.

## Rules

1. **Only modify `frontend/` and `backend/`.** Do not write outside those paths, even to
   "fix" a doc, config, or script.
2. **Read-only elsewhere.** Reading files outside the two folders for context is allowed;
   changing them is not.
3. **Stop if blocked.** If a task genuinely requires a change outside `frontend/` or
   `backend/`, do not make it — explain what is needed and ask the user first.
4. **Ignore generated content.** Never edit `frontend/node_modules/`, `backend/.venv/`,
   build output (`frontend/dist/`), caches (`__pycache__/`, `.pytest_cache/`), or lockfiles by
   hand.
5. **Verify within scope.** Run frontend checks from `frontend/` and backend checks from
   `backend/`; do not run commands that rewrite files outside those folders.
6. **Stage only in-scope files.** When committing, include only paths under `frontend/` or
   `backend/`.
