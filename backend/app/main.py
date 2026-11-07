from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.db import init_db
from app.services.pipeline import calibrate, infer


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.model = infer.load_model()
    app.state.temperature = calibrate.load_temperature()
    app.state.thresholds = calibrate.load_thresholds()
    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
