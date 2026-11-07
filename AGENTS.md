# AGENTS.md — reguli pentru orice agent AI care lucrează în acest repo

Proiect: **SolarTriage**. Spec-ul complet e în `docs/DESIGN_SPEC.md`. Taskurile sunt în `.scratch/solartriage/` (harta e în `map.md`, tichetele în `issues/`).

## Stack — OBLIGATORIU, NU SE NEGOCIAZĂ

- **Backend: DOAR Python + FastAPI**, în `backend/`. Modelul ML, pipeline-ul, stratul de decizie și toate acțiunile rulează în FastAPI.
- **Frontend: DOAR React (Vite + TypeScript)**, în `frontend/`. React doar afișează date și trimite acțiuni către FastAPI. Logica de business stă în backend.
- **Comunicare:** doar HTTP/JSON și SSE, prin FastAPI, sub prefixul `/api`.
- **INTERZIS:** Flask, Django, Starlette direct, Node/Express/Nest pe backend, Next.js, Remix, Vue, Svelte, Angular, Streamlit, Gradio, notebook-uri folosite ca server, inferență ML în browser, HTML/JS vanilla în loc de componente React.
- **Nu schimba stack-ul și nu propune alternative**, nici dacă par mai simple. Dacă un task pare să ceară alt framework, oprește-te și întreabă omul.

## Biblioteci permise (nu adăuga altele fără să întrebi)

- Backend: `fastapi`, `sqlmodel`, `pydantic`, `pydantic-settings`, `httpx`, `numpy`, `onnxruntime`, `pyyaml`, `jinja2`, `pillow`, `pytest`, `ruff`.
- Antrenare, doar în `ml/`: `torch`, `torchvision`, `scikit-learn`, `onnx`.
- Frontend: `react`, `react-dom`, `react-router-dom`, `zustand`, `recharts`, `tailwindcss`, `openapi-typescript`, `@playwright/test`.

## Reguli de cod

- **Niciun fișier sursă peste 30 KB** (30.720 bytes). Când un fișier se apropie de limită, sparge-l pe responsabilități. Verificarea e în `backend/tests/test_file_size.py`.
- Scrie cea mai simplă variantă corectă. Fără abstracții „pentru viitor” și fără cod duplicat între backend și frontend.
- Schemele API sunt Pydantic, în `backend/app/schemas/`. Tipurile TypeScript se **generează** din `/api/openapi.json`. Nu le scrie de mână.
- Nu inventa endpoint-uri, câmpuri sau clase care nu sunt în `docs/DESIGN_SPEC.md`. Dacă lipsește ceva, scrie o notă în tichet și întreabă.
- Rulează testele înainte de a declara un task gata: `cd backend && uv run pytest -q` și `cd frontend && npm run build`.
- Nu face commit pe `main`. Lucrează pe ramura ta, cu commit-uri mici.
