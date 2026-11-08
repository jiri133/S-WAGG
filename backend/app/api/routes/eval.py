from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas import EvalReport

router = APIRouter(tags=["eval"])

EVAL_JSON = Path(__file__).resolve().parents[4] / "reports" / "eval.json"


@router.get("/eval")
def get_eval() -> EvalReport:
    """Serves reports/eval.json written by evaluate.py (§3.6)."""
    if not EVAL_JSON.exists():
        raise HTTPException(404, "reports/eval.json nu a fost generat încă; rulează evaluate.py")
    return EvalReport.model_validate_json(EVAL_JSON.read_text(encoding="utf-8"))
