"""Tune the rules baseline (Baseline A) on train and score it on val.

Coordinate descent: each threshold in turn takes the value, among quantiles of
its feature on train, that gives the best train macro-F1. Writes
backend/config/baseline_rules.json. Test is never read here (it is for evaluate.py).

    uv run --project ml python ml/tune_rules.py
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.baseline.features import FEATURE_NAMES, load_crop, vector
from app.services.baseline.rules_classifier import (
    CLASSES,
    RULES,
    THRESHOLDS_PATH,
    load_thresholds,
    predict,
)

# Hand-set start, in the PoC's spirit (gray levels, not kelvin).
START = {
    "diode_contrast": 15, "diode_cover": 0.9,
    "offline_frame": 45, "offline_peak": 20, "offline_uniform": 0.6,
    "other_hot_frac": 0.15, "other_cells": 6,
    "soiling_peak": 40, "soiling_cover": 0.6, "soiling_top": 5,
    "multi_blobs": 2, "multi_peak": 25,
    "hot_peak": 20,
    "shadow_rows": 25, "shadow_cold": 0.2,
}
PASSES = 4


def split_features(split: str) -> tuple[np.ndarray, np.ndarray]:
    """Feature matrix and class labels for ml/splits/<split>.csv."""
    with open(ROOT / "ml" / "splits" / f"{split}.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    X = np.stack([vector(load_crop(ROOT / r["path"])) for r in rows])
    return X, np.array([r["class"] for r in rows])


def macro_f1(y, pred) -> float:
    return f1_score(y, pred, labels=CLASSES, average="macro", zero_division=0)


def tune(X: np.ndarray, y: np.ndarray, start: dict[str, float]) -> dict[str, float]:
    """Coordinate descent on train macro-F1; each threshold tries 41 quantiles of its feature."""
    feature_of = {key: f for _, conds in RULES for f, _, key in conds}
    th = dict(start)
    best = macro_f1(y, predict(X, th))
    for _ in range(PASSES):
        for key, feature in feature_of.items():
            col = X[:, FEATURE_NAMES.index(feature)]
            for value in np.unique(np.quantile(col, np.linspace(0, 1, 41))):
                trial = {**th, key: round(float(value), 4)}
                score = macro_f1(y, predict(X, trial))
                if score > best:
                    best, th = score, trial
        print(f"pass done, train macro-F1 {best:.4f}")
    return th


def report(name: str, y, pred) -> None:
    per_class = f1_score(y, pred, labels=CLASSES, average=None, zero_division=0)
    print(f"{name}: val macro-F1 {macro_f1(y, pred):.3f}")
    for c, f in zip(CLASSES, per_class, strict=True):
        print(f"  {c:18s} {f:.3f}")


def main() -> None:
    X, y = split_features("train")
    print(f"train macro-F1 at start {macro_f1(y, predict(X, START)):.4f}")
    th = tune(X, y, START)
    THRESHOLDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    THRESHOLDS_PATH.write_text(json.dumps(th, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {THRESHOLDS_PATH.relative_to(ROOT)}")
    Xv, yv = split_features("val")
    report("rules", yv, predict(Xv, load_thresholds()))


if __name__ == "__main__":
    main()
