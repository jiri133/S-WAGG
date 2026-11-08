"""Battery dispatch reports and PV forecast metrics from the ``RL/`` package."""

from fastapi import APIRouter, HTTPException

from app.schemas.pv_eval import PvEvalReport
from app.schemas.rl_eval import RlEvalReport
from app.services import pv_reports
from app.services.rl_reports import load_reports

router = APIRouter(tags=["eval"])


@router.get("/eval/rl", response_model=RlEvalReport)
def get_rl_eval() -> RlEvalReport:
    """Summary tables from ``RL/artifacts/reports/<split>/results.csv``."""
    return load_reports()


@router.get("/eval/pv", response_model=PvEvalReport)
def get_pv_eval() -> PvEvalReport:
    """Training metrics from ``RL/artifacts/models/pv/metrics.json``."""
    try:
        return pv_reports.load_metrics()
    except FileNotFoundError as exc:
        raise HTTPException(
            404, "Metricile prognozei PV nu au fost generate încă; rulează train_pv.py"
        ) from exc
