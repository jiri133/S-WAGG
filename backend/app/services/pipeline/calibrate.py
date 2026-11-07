"""Step 5 (DESIGN_SPEC §3.4, §5): temperature + per-severity thresholds → `unsure` and why.

Ticket 09 (ml/calibrate.py) writes artifacts/temperature.json and thresholds.json.
Until then the defaults below are used; they are the only copy of them.
"""

import json
from pathlib import Path

import numpy as np

from app.schemas import Prediction
from app.services.pipeline.infer import ARTIFACTS, CLASSES

DEFAULT_TEMPERATURE = 1.0
DEFAULT_THRESHOLDS = {
    "risk_classes": ["hot_cell", "multi_hot", "diode_substring"],
    "min_conf": {"risk": 0.7, "other": 0.6},  # top probability needed to pass automatically
    "ok_max_risk": 0.15,  # an `ok` with this much on one risk class still goes to the queue
}


def load_temperature(path: Path = ARTIFACTS / "temperature.json") -> float:
    if not path.exists():
        return DEFAULT_TEMPERATURE
    return float(json.loads(path.read_text(encoding="utf-8"))["temperature"])


def load_thresholds(path: Path = ARTIFACTS / "thresholds.json") -> dict:
    if not path.exists():
        return DEFAULT_THRESHOLDS
    return json.loads(path.read_text(encoding="utf-8"))


def unsure_reason(p: np.ndarray, th: dict) -> str | None:
    """None when the prediction passes automatically, else the reason it goes to the queue."""
    top = CLASSES[int(p.argmax())]
    risk = th["risk_classes"]
    if top == "ok":
        worst = max(risk, key=lambda c: p[CLASSES.index(c)])
        if p[CLASSES.index(worst)] >= th["ok_max_risk"]:
            return f"ok, dar {p[CLASSES.index(worst)]:.2f} pe {worst} (clasă de risc)"
    group = "risk" if top in risk else "other"
    if p.max() < th["min_conf"][group]:
        return f"încredere {p.max():.2f} sub pragul {th['min_conf'][group]:.2f} ({group})"
    return None


def predictions(probs: np.ndarray, temperature: float, th: dict) -> list[Prediction]:
    out = []
    for p in probs:
        reason = unsure_reason(p, th)
        out.append(
            Prediction(
                cls=CLASSES[int(p.argmax())],
                probs={c: round(float(v), 4) for c, v in zip(CLASSES, p, strict=True)},
                temperature=temperature,
                unsure=reason is not None,
                unsure_reason=reason,
            )
        )
    return out
