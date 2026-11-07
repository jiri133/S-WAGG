"""Shape of reports/eval.json, written by evaluate.py and served by GET /eval (§3.6)."""

from pydantic import BaseModel

from app.schemas.park import FaultClass


class ModelScores(BaseModel):
    name: str  # rules | random_forest | resnet18
    macro_f1: float  # on the 8 classes
    accuracy: float
    f1_per_class: dict[FaultClass, float]
    # The models predict 8 classes, so on the 12 Raptor classes only recall is defined:
    # share of each Raptor class predicted as its mapped class.
    recall_12: dict[str, float]
    macro_recall_12: float
    confusion: list[list[int]]  # rows = truth, columns = prediction, in `classes` order


class ReliabilityBin(BaseModel):
    lo: float
    hi: float
    n: int
    conf: float
    acc: float


class Calibration(BaseModel):
    temperature: float
    ece_before: float
    ece_after: float
    bins_before: list[ReliabilityBin]
    bins_after: list[ReliabilityBin]


class RiskPoint(BaseModel):
    coverage: float
    risk: float
    conf: float


class ClassAuto(BaseModel):
    auto: int
    precision: float | None


class Selective(BaseModel):
    """What the thresholds from thresholds.json let through automatically on test."""

    target_precision: float
    coverage: float
    precision_auto: float
    per_class: dict[FaultClass, ClassAuto]


class ErrorExample(BaseModel):
    image_id: str
    conf: float
    crop_png: str  # data:image/png;base64 URI of the 24×40 crop


class TopConfusion(BaseModel):
    truth: FaultClass
    pred: FaultClass
    count: int
    examples: list[ErrorExample]


class EvalReport(BaseModel):
    split: str
    n: int
    classes: list[FaultClass]
    support: dict[FaultClass, int]
    models: list[ModelScores]
    calibration: Calibration
    risk_coverage: list[RiskPoint]
    selective: Selective
    errors: list[TopConfusion]
    notes: list[str]
