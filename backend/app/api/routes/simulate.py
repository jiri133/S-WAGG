"""Run a planning day for the trained farm (web visualization)."""

from fastapi import APIRouter, HTTPException

from app.schemas.simulation import SimulationRequest, SimulationResponse
from app.services.rl_simulation import SimulationError, run_simulation

router = APIRouter(prefix="/simulate", tags=["simulate"])


@router.post("", response_model=SimulationResponse)
def simulate(payload: SimulationRequest) -> SimulationResponse:
    try:
        result = run_simulation(
            strategy=payload.strategy,
            split=payload.split,
            day=payload.day,
            seed=payload.seed,
        )
    except SimulationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return SimulationResponse.model_validate(result)
