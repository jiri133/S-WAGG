"""Shape of the PV forecast metrics read from ``RL/artifacts/models/pv/metrics.json``."""

from pydantic import BaseModel


class PvLeadMetrics(BaseModel):
    lead: str
    n: int
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None


class PvSplitMetrics(BaseModel):
    split: str
    n: int
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    persistence_mae: float | None = None
    by_lead: list[PvLeadMetrics] = []


class PvEvalReport(BaseModel):
    model: str
    version: str
    trained_at_utc: str | None = None
    farm: str | None = None
    rows: int | None = None
    n_features: int
    splits: list[PvSplitMetrics]
