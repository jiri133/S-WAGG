"""Missions and drone frames (DESIGN_SPEC §9)."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.park import FaultClass, Module, ModuleStatus


class MissionSettings(BaseModel):
    # Bounds keep the simulator valid: numpy seeds are >= 0 and the park has 480 modules.
    seed: int = Field(7, ge=0)
    n_faults: int = Field(12, ge=0, le=480)
    p_cloud: float = Field(0.10, ge=0, le=1)
    p_gps: float = Field(0.06, ge=0, le=1)
    p_glare: float = Field(0.10, ge=0, le=1)
    p_lost: float = Field(0.03, ge=0, le=1)
    inject: list[Literal["rgb", "no_panels", "low_irr", "missing"]] = []
    speed: float = Field(1.0, gt=0)


class Mission(BaseModel):
    id: str
    settings: MissionSettings
    phase: Literal["planned", "flying", "checked", "analysed", "reviewed", "done"]
    modules: list[Module]
    status: dict[str, ModuleStatus]
    truth: dict[str, FaultClass] | None = None  # only in demo mode


class FrameMeta(BaseModel):
    id: str
    table: str
    pass_no: Literal[1, 2]
    file: str
    timestamp: str
    lat: float
    lon: float
    irradiance_wm2: float
    wind_ms: float
    channels: int
    radiometric: bool
    check_ok: bool
    problems: list[str]
    gps_offset_detected: int  # modules; 0 = aligned
    thumb_url: str
