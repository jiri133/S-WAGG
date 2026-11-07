from fastapi import APIRouter

from app.api.routes import actions, findings, health, missions, mock, park
from app.api.routes import eval as eval_routes

# Mounted under /api in main.py. Endpoints follow DESIGN_SPEC §9.
api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(park.router)
api_router.include_router(missions.router)
api_router.include_router(findings.router)
api_router.include_router(actions.router)
api_router.include_router(mock.router)
api_router.include_router(eval_routes.router)
