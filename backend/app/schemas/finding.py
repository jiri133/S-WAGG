"""Model predictions, evidence and findings (DESIGN_SPEC §9)."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.park import FaultClass, Urgency

ReviewDecision = Literal["confirmed", "rejected", "inconclusive"]


class Prediction(BaseModel):
    cls: FaultClass
    probs: dict[FaultClass, float]
    temperature: float
    unsure: bool
    unsure_reason: str | None = None


class SimilarCase(BaseModel):
    id: str
    cls: FaultClass
    crop_url: str
    distance: float


class Evidence(BaseModel):
    frame_ids: list[str]
    crop_url: str
    gradcam_url: str | None = None
    delta_t_k: float
    pattern: str
    seen_in_both_passes: bool
    similar: list[SimilarCase] = []
    rule_applied: str


class Finding(BaseModel):
    id: str
    module_id: str
    prediction: Prediction
    baseline_cls: FaultClass
    urgency: Urgency
    loss_kwh_day: float
    loss_ron_day: float
    score: float
    crew: Literal["electrical", "cleaning"]
    part: str | None
    est_hours: float
    evidence: Evidence
    review: ReviewDecision | None = None
    review_note: str | None = None


class ReviewIn(BaseModel):
    decision: ReviewDecision
    note: str | None = None
