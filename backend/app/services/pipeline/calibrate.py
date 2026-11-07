"""Step 5 (DESIGN_SPEC §3.4, §5): temperature + per-class thresholds → `unsure` and why.

ml/calibrate.py (ticket 09) writes artifacts/temperature.json and thresholds.json with the same
rule as `unsure_reason`: unsure if p[top] < min_conf[top], or top is `ok` and the summed
probability on the risk classes exceeds max_risk_prob_ok. Defaults apply when files are missing.
"""

import json
from pathlib import Path

import numpy as np

from app.schemas import Prediction
from app.services.pipeline.infer import ARTIFACTS, CLASSES

RISK_CLASSES = ["hot_cell", "multi_hot", "diode_substring"]
DEFAULT_TEMPERATURE = 1.0
DEFAULT_THRESHOLDS = {
    "risk_classes": RISK_CLASSES,
    "max_risk_prob_ok": 0.15,
    "min_conf": {c: 0.7 if c in RISK_CLASSES else 0.6 for c in CLASSES},
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
    if top == "ok":
        risk = sum(p[CLASSES.index(c)] for c in th["risk_classes"])
        if risk > th["max_risk_prob_ok"]:
            return f"ok, dar {risk:.2f} pe clasele de risc"
    need = th["min_conf"][top]
    if p.max() < need:
        return f"încredere {p.max():.2f} sub pragul {min(need, 1.0):.2f} pentru {top}"
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
