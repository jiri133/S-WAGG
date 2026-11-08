"""Farm configuration CRUD and YAML export."""

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import SessionDep
from app.core.config import settings
from app.models.farm import FarmConfig as FarmConfigModel
from app.models.farm import utcnow
from app.schemas.farm import (
    ExportResult,
    FarmConfigCreate,
    FarmConfigRead,
    FarmConfigUpdate,
)
from app.services.farm_config import export_farm_config

router = APIRouter(prefix="/farms", tags=["farms"])


def _get_farm(session: SessionDep, farm_id: int) -> FarmConfigModel:
    farm = session.get(FarmConfigModel, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm configuration not found")
    return farm


def _read(farm: FarmConfigModel) -> FarmConfigRead:
    return FarmConfigRead.model_validate(farm)


@router.get("", response_model=list[FarmConfigRead])
def list_farms(session: SessionDep) -> list[FarmConfigRead]:
    farms = session.exec(select(FarmConfigModel).order_by(FarmConfigModel.id)).all()
    return [_read(farm) for farm in farms]


@router.post("", response_model=FarmConfigRead, status_code=201)
def create_farm(payload: FarmConfigCreate, session: SessionDep) -> FarmConfigRead:
    is_first = session.exec(select(FarmConfigModel)).first() is None
    farm = FarmConfigModel(**payload.model_dump(), active=is_first)
    session.add(farm)
    session.commit()
    session.refresh(farm)
    if farm.active:
        export_farm_config(farm, settings.rl_config_dir)
    return _read(farm)


@router.get("/active", response_model=FarmConfigRead)
def get_active_farm(session: SessionDep) -> FarmConfigRead:
    farm = session.exec(
        select(FarmConfigModel).where(FarmConfigModel.active == True)  # noqa: E712
    ).first()
    if farm is None:
        raise HTTPException(status_code=404, detail="No active farm configuration")
    return _read(farm)


@router.get("/{farm_id}", response_model=FarmConfigRead)
def get_farm(farm_id: int, session: SessionDep) -> FarmConfigRead:
    return _read(_get_farm(session, farm_id))


@router.put("/{farm_id}", response_model=FarmConfigRead)
def update_farm(
    farm_id: int,
    payload: FarmConfigUpdate,
    session: SessionDep,
) -> FarmConfigRead:
    farm = _get_farm(session, farm_id)
    for key, value in payload.model_dump().items():
        setattr(farm, key, value)
    farm.updated_at = utcnow()
    session.add(farm)
    session.commit()
    session.refresh(farm)
    if farm.active:
        export_farm_config(farm, settings.rl_config_dir)
    return _read(farm)


@router.post("/{farm_id}/activate", response_model=ExportResult)
def activate_farm(farm_id: int, session: SessionDep) -> ExportResult:
    farm = _get_farm(session, farm_id)
    now = utcnow()
    for other in session.exec(select(FarmConfigModel)).all():
        other.active = other.id == farm.id
        other.updated_at = now
        session.add(other)
    session.commit()
    session.refresh(farm)

    path, checksum = export_farm_config(farm, settings.rl_config_dir)
    return ExportResult(path=str(path), checksum=checksum, farm=_read(farm))
