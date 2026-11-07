"""Test-set metrics for evaluate.py (DESIGN_SPEC §3.6), numpy only.

Labels are class indices into a fixed class list; probabilities are (n, k) rows that sum to 1.
"""

import numpy as np


def confusion(y: np.ndarray, pred: np.ndarray, k: int) -> np.ndarray:
    """(k, k) counts, rows = truth, columns = prediction."""
    cm = np.zeros((k, k), dtype=int)
    np.add.at(cm, (y, pred), 1)
    return cm


def f1_per_class(cm: np.ndarray) -> np.ndarray:
    """F1 per class from a confusion matrix; 0 where a class is never true nor predicted."""
    tp = np.diag(cm).astype(float)
    denom = cm.sum(axis=0) + cm.sum(axis=1)
    return np.divide(2 * tp, denom, out=np.zeros_like(tp), where=denom > 0)


def reliability(probs: np.ndarray, y: np.ndarray, n_bins: int = 15) -> list[dict]:
    """Equal-width confidence bins: count, mean confidence, accuracy (same as ml/calibrate.py)."""
    conf, correct = probs.max(axis=1), probs.argmax(axis=1) == y
    idx = np.minimum((conf * n_bins).astype(int), n_bins - 1)
    bins = []
    for b in range(n_bins):
        m = idx == b
        n = int(m.sum())
        bins.append({"lo": b / n_bins, "hi": (b + 1) / n_bins, "n": n,
                     "conf": float(conf[m].mean()) if n else 0.0,
                     "acc": float(correct[m].mean()) if n else 0.0})
    return bins


def ece(probs: np.ndarray, y: np.ndarray, n_bins: int = 15) -> float:
    bins = reliability(probs, y, n_bins)
    return float(sum(b["n"] * abs(b["acc"] - b["conf"]) for b in bins) / len(y))


def risk_coverage(conf: np.ndarray, correct: np.ndarray, n_points: int = 50) -> list[dict]:
    """Keep the most confident cases first: error rate among the kept ones vs. share kept."""
    order = np.argsort(-conf, kind="stable")
    errors = np.cumsum(~correct[order])
    kept = np.arange(1, len(conf) + 1)
    picks = np.unique(np.linspace(1, len(conf), n_points).round().astype(int)) - 1
    return [{"coverage": float(kept[i] / len(conf)), "risk": float(errors[i] / kept[i]),
             "conf": float(conf[order][i])} for i in picks]


def top_confusions(cm: np.ndarray, n: int = 5) -> list[tuple[int, int, int]]:
    """The n largest off-diagonal cells as (truth, prediction, count), largest first."""
    off = [(int(cm[i, j]), i, j) for i in range(len(cm)) for j in range(len(cm)) if i != j]
    return [(i, j, c) for c, i, j in sorted(off, reverse=True)[:n] if c > 0]
