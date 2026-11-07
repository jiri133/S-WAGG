"""Baseline A: the PoC's classify() on intensity features, extended to the 8 classes.

A fixed-order decision list: the first rule whose conditions all hold wins,
otherwise the crop is `ok`. Pattern first, then size, as in the PoC. The
threshold values live in config/baseline_rules.json and are tuned on train
by ml/tune_rules.py.
"""

import json
from pathlib import Path

import numpy as np

from .features import FEATURE_NAMES, vector

THRESHOLDS_PATH = Path(__file__).resolve().parents[3] / "config" / "baseline_rules.json"

# (class, [(feature, ">=" or "<=", threshold key)]), checked in this order.
RULES = [
    # one substring uniformly warmer than the other two: bypass diode
    ("diode_substring", [("band_contrast", ">=", "diode_contrast"),
                         ("band_cover", ">=", "diode_cover")]),
    # whole module warmer than its surroundings, no hot spot: open circuit
    ("module_offline", [("frame_contrast", ">=", "offline_frame"), ("peak", "<=", "offline_peak"),
                        ("uniform_frac", ">=", "offline_uniform")]),
    # large irregular hot area over many cells: cracking and the rest
    ("other", [("hot_frac", ">=", "other_hot_frac"), ("n_hot_cells", ">=", "other_cells")]),
    # warm patch that spreads along an edge instead of a cell
    ("soiling", [("peak", ">=", "soiling_peak"), ("band_cover", "<=", "soiling_cover"),
                 ("top_delta", ">=", "soiling_top")]),
    ("multi_hot", [("n_blobs", ">=", "multi_blobs"), ("peak", ">=", "multi_peak")]),
    ("hot_cell", [("peak", ">=", "hot_peak")]),
    # weak, uneven warmth without a clear spot: shadow or vegetation
    ("shadow_vegetation", [("row_spread", ">=", "shadow_rows"),
                           ("cold_frac", ">=", "shadow_cold")]),
]
CLASSES = ["ok", "hot_cell", "multi_hot", "diode_substring", "module_offline", "soiling",
           "shadow_vegetation", "other"]


def load_thresholds(path: Path = THRESHOLDS_PATH) -> dict[str, float]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def predict(X: np.ndarray, thresholds: dict[str, float]) -> np.ndarray:
    """Class names for a (n, len(FEATURE_NAMES)) feature matrix."""
    X = np.atleast_2d(X)
    out = np.full(len(X), "ok", dtype=object)
    free = np.ones(len(X), dtype=bool)
    for cls, conditions in RULES:
        hit = free.copy()
        for feature, op, key in conditions:
            col = X[:, FEATURE_NAMES.index(feature)]
            hit &= col >= thresholds[key] if op == ">=" else col <= thresholds[key]
        out[hit] = cls
        free &= ~hit
    return out


def classify(crop: np.ndarray, thresholds: dict[str, float] | None = None) -> str:
    """Baseline class of one (40, 24) gray crop."""
    return str(predict(vector(crop), thresholds or load_thresholds())[0])
