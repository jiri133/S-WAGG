# Opțional: LLM pentru rezumatul raportului

Type: task
Status: resolved
Owner: Alina
Țintă: după H20
Blocked by: 24

## Question

Spec: §2 și decizia Q13. Flag `REPORT_LLM=1`, primește doar JSON-ul cu cifrele, fallback pe template. Dacă apare un număr care nu e în JSON, se folosește template-ul.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Code freeze H20: verificare cap-coadă](24-code-freeze.md)

## Answer

Implementat pe ramura `feat/29-opt-llm`, pornită explicit din `docs/design-spec` (`aaf7726`): worktree-ul era pe `main` (`1b61c9c`), care nu conținea `services/report/` din tichetele 17–24.

- `backend/app/core/config.py`: `report_llm: bool = False`; pydantic-settings citește `REPORT_LLM` din env/`.env`. Implicit oprit, deci raportul rămâne template-ul Jinja2 de dinainte.
- `backend/app/services/report/llm.py`: construiește un JSON doar cu faptele raportului (misiune, finding-uri, ordine de lucru, plan, alerte — fără crop-uri, probabilități sau review-uri), îl trimite prin `httpx.post` către Anthropic (`claude-opus-5-5`) sau OpenAI (`gpt-4o-mini`), cu timeout de 5 s; fără SDK și fără dependențe noi. Orice eroare HTTP, timeout sau răspuns invalid → `None`, fără excepție din endpoint.
- Validarea Q13: fiecare număr din textul LLM trebuie să existe ca token numeric în JSON-ul trimis (virgula zecimală normalizată); un număr inventat → fallback pe template.
- `report.html.j2`: secțiunea „Rezumat” apare doar când sumarul a trecut validarea.
- `backend/tests/test_report_llm.py`: 7 teste — flag off nu face niciun HTTP; sumar valid apare în HTML; număr inventat → fallback; timeout HTTP → fallback; fără cheie → fallback; ramura OpenAI; potrivirea numerelor întregi.

Verificare (comenzi și rezultate):

- `cd backend && uv run pytest -q` → `198 passed, 1 skipped` (înainte de modificare: `191 passed, 1 skipped`).
- `cd backend && uv run ruff check .` → `All checks passed!`
- `cd frontend && npm run build` → `✓ built in 410ms` (warning-ul de chunk > 500 kB e preexistent).
- Endpoint real: `REPORT_LLM=1 uv run uvicorn app.main:app --port 8123`, apoi `curl http://127.0.0.1:8123/api/missions/M-0001/report` → `HTTP 200`, HTML-ul are titlul raportului și nu are secțiunea „Rezumat” (niciun key configurat → fallback). Serverul a fost oprit după verificare.
- `REPORT_LLM=1 uv run python -c "..."` → `report_llm= True | anthropic_key= None | openai_key= None`, deci flagul se parsează, iar verificarea pe server nu a putut apela nicio API reală. Toate testele monkeypatch-uiesc `httpx.post`; niciun apel real nu a fost făcut.
- `uv sync` a fost rulat pentru că worktree-ul nu avea `.venv` (Python 3.14.10 era deja instalat prin uv).
