"""Battery evaluation reports produced by ``RL/scripts/evaluate.py``."""

from fastapi import APIRouter

from app.schemas.rl_eval import RlEvalReport
from app.services.rl_reports import load_reports

router = APIRouter(tags=["eval"])


@router.get("/eval/rl", response_model=RlEvalReport)
def get_rl_eval() -> RlEvalReport:
    """Summary tables from ``RL/artifacts/reports/<split>/results.csv``."""
    return load_reports()
