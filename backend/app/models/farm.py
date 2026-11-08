"""SQLModel table for a farm configuration."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp (SQLModel's UTCDateTime requires it)."""
    return datetime.now(UTC)


class FarmConfig(SQLModel, table=True):
    __tablename__ = "farm_configs"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, min_length=1)
    latitude: float
    longitude: float

    pv_kwp: float
    inverter_ac_mw: float
    tilt_deg: float
    azimuth_deg: float
    tracking: str = "none"

    battery_capacity_mwh: float
    battery_p_max_mw: float
    soc_min: float = 0.1
    soc_max: float = 0.9
    eta_charge: float = 0.95
    eta_discharge: float = 0.95

    asset_scale: float = 1.0
    export_limit_mw: float | None = None
    import_limit_mw: float | None = None

    metered_pv_path: str | None = None
    timezone: str = "Europe/Bucharest"
    notes: str | None = None

    active: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
