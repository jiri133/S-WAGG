# Python 3.15 merge cu PyTorch, ONNX Runtime și numpy?

Type: research
Status: resolved
Owner: agent (AFK)
Țintă: H0
Blocked by: —

## Question

Pe laptop e instalat doar Python 3.15. Au `torch`, `torchvision`, `onnxruntime`, `numpy`, `scikit-learn` și `pillow` wheel-uri pentru Windows x64 pe Python 3.15?

Dacă nu: ce versiune fixăm în `backend/.python-version` (și pentru `ml/`), ca `uv` să o instaleze singur pe ambele laptopuri?

**Gata când:** există o notă cu sursele (PyPI, release notes) și o recomandare de versiune.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

## Answer

**Fixăm Python 3.14** (`cd backend && uv python pin 3.14`, la fel pentru `ml/`) și punem `requires-python = ">=3.11,<3.15"` în `backend/pyproject.toml`. Pe 3.15 lipsesc wheel-urile Windows pentru `onnxruntime` (1.31.1 are doar cp311–cp314) și `PyYAML` (6.0.3, doar până la cp314). Restul pachetelor merg și pe 3.14. Evităm 3.14.1, pe care torchvision îl exclude. `uv` descarcă singur 3.14.x și ignoră 3.15 de pe sistem.

Detalii și surse: branch-ul `research/python-compat` (commit c4ac855), fișierul `.scratch/solartriage/research/01-python-compat.md`.