"""Run a planning day for the trained farm (web visualization)."""

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.schemas.simulation import (
    SimulationDerate,
    SimulationRequest,
    SimulationResponse,
)
from app.services import production
from app.services.rl_simulation import SimulationError, run_simulation

router = APIRouter(prefix="/simulate", tags=["simulate"])


@router.get("/derate", response_model=SimulationDerate)
def current_derate(session: SessionDep) -> SimulationDerate:
    """Production impact of the latest inspection, before running a day."""
    return production.current(session)


@router.post("", response_model=SimulationResponse)
def simulate(payload: SimulationRequest, session: SessionDep) -> SimulationResponse:
    derate = production.current(session)
    try:
        result = run_simulation(
            strategy=payload.strategy,
            split=payload.split,
            day=payload.day,
            seed=payload.seed,
            pv_factor=derate.factor,
        )
    except SimulationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return SimulationResponse.model_validate(
        {**result, "derate": derate.model_dump()}
    )
