from fastapi import APIRouter

from app.schemas import Module
from app.services.sim.park import park

router = APIRouter(tags=["park"])


@router.get("/park")
def get_park() -> list[Module]:
    """The 480 modules of the park (§4 layout)."""
    return park()
