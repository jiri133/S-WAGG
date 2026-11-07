"""Missions and drone frames (DESIGN_SPEC §9)."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.park import FaultClass, Module, ModuleStatus


class MissionSettings(BaseModel):
    seed: int = 7
    n_faults: int = 12
    p_cloud: float = 0.10
    p_gps: float = 0.06
    p_glare: float = 0.10
    p_lost: float = 0.03
    inject: list[Literal["rgb", "no_panels", "low_irr", "missing"]] = []
    speed: float = 1.0


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
