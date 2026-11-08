"""Request/response schemas for farm configuration.

The flat API shape mirrors the SQLModel table. ``to_rl_dict`` produces the nested YAML shape
consumed by ``RL/src/battery_rl/config.py``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

Tracking = Literal["none", "single_axis", "dual_axis"]

# ENTSO-E RO 2026 actual-load peak, used only for the UI warning.
NATIONAL_PEAK_MW = 9296.0


class FarmConfigBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    pv_kwp: float = Field(gt=0)
    inverter_ac_mw: float = Field(gt=0)
    tilt_deg: float = Field(ge=0, le=90)
    azimuth_deg: float = Field(ge=0, le=360, description="0=N, 90=E, 180=S, 270=W")
    tracking: Tracking = "none"

    battery_capacity_mwh: float = Field(gt=0)
    battery_p_max_mw: float = Field(gt=0)
    soc_min: float = Field(ge=0, lt=1)
    soc_max: float = Field(gt=0, le=1)
    eta_charge: float = Field(gt=0, le=1)
    eta_discharge: float = Field(gt=0, le=1)

    asset_scale: float = Field(default=1.0, gt=0)
    export_limit_mw: float | None = Field(default=None, gt=0)
    import_limit_mw: float | None = Field(default=None, gt=0)

    metered_pv_path: str | None = None
    timezone: str = "Europe/Bucharest"
    notes: str | None = None

    @model_validator(mode="after")
    def _check_soc_range(self) -> FarmConfigBase:
        if self.soc_min >= self.soc_max:
            raise ValueError("soc_min must be strictly less than soc_max")
        return self

    def to_rl_dict(self) -> dict:
        """Nested config matching ``battery_rl.config.FarmConfig``."""
        return {
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "asset_scale": self.asset_scale,
            "pv": {
                "kwp": self.pv_kwp,
                "inverter_ac_mw": self.inverter_ac_mw,
                "tilt_deg": self.tilt_deg,
                "azimuth_deg": self.azimuth_deg,
                "tracking": self.tracking,
            },
            "battery": {
                "capacity_mwh": self.battery_capacity_mwh,
                "p_max_mw": self.battery_p_max_mw,
                "soc_min": self.soc_min,
                "soc_max": self.soc_max,
                "eta_charge": self.eta_charge,
                "eta_discharge": self.eta_discharge,
            },
            "grid": {
                "export_limit_mw": self.export_limit_mw,
                "import_limit_mw": self.import_limit_mw,
            },
            "metered_pv_path": self.metered_pv_path,
            "timezone": self.timezone,
            "notes": self.notes,
        }

    def canonical_checksum(self) -> str:
        canonical = json.loads(json.dumps(self.to_rl_dict(), sort_keys=True))
        text = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FarmConfigCreate(FarmConfigBase):
    pass


class FarmConfigUpdate(FarmConfigBase):
    pass


class FarmConfigRead(FarmConfigBase):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def scaled_pv_kwp(self) -> float:
        return self.pv_kwp * self.asset_scale

    @computed_field
    @property
    def scaled_inverter_ac_mw(self) -> float:
        return self.inverter_ac_mw * self.asset_scale

    @computed_field
    @property
    def scaled_battery_capacity_mwh(self) -> float:
        return self.battery_capacity_mwh * self.asset_scale

    @computed_field
    @property
    def scaled_p_max_mw(self) -> float:
        return self.battery_p_max_mw * self.asset_scale

    @computed_field
    @property
    def battery_pct_of_national_peak(self) -> float:
        return 100.0 * self.battery_p_max_mw * self.asset_scale / NATIONAL_PEAK_MW


class ExportResult(BaseModel):
    path: str
    checksum: str
    farm: FarmConfigRead
