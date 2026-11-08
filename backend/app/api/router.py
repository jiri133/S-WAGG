from fastapi import APIRouter

from app.api.routes import (
    actions,
    farms,
    findings,
    health,
    missions,
    mock,
    park,
    simulate,
)
from app.api.routes import eval as eval_routes
from app.api.routes import rl_eval as rl_eval_routes

# Mounted under /api in main.py. Endpoints follow DESIGN_SPEC §9.
api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(farms.router)
api_router.include_router(simulate.router)
api_router.include_router(park.router)
api_router.include_router(missions.router)
api_router.include_router(findings.router)
api_router.include_router(actions.router)
api_router.include_router(mock.router)
api_router.include_router(eval_routes.router)
api_router.include_router(rl_eval_routes.router)
