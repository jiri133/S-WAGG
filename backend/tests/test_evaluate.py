"""Metrics (services/metrics.py) and the evaluate.py helpers, on small synthetic data."""

import sys
from pathlib import Path

import numpy as np
import pytest

from app.services import metrics
from app.services.pipeline.calibrate import DEFAULT_THRESHOLDS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import evaluate  # noqa: E402

Y = np.array([0, 0, 0, 1, 1, 2])
PRED = np.array([0, 0, 1, 1, 2, 2])


def test_confusion_counts_rows_truth_columns_pred():
    cm = metrics.confusion(Y, PRED, 3)
    assert cm.tolist() == [[2, 1, 0], [0, 1, 1], [0, 0, 1]]


def test_f1_per_class_by_hand():
    f1 = metrics.f1_per_class(metrics.confusion(Y, PRED, 4))
    # class 0: tp 2, fp 0, fn 1 → 0.8; class 1: tp 1, fp 1, fn 1 → 0.5; class 2: 2/3; class 3 unused
    assert f1 == pytest.approx([0.8, 0.5, 2 / 3, 0.0])


def test_ece_zero_when_confidence_matches_accuracy():
    # confidence 0.75 everywhere, 3 of 4 right
    p = np.array([[0.75, 0.25]] * 4)
    assert metrics.ece(p, np.array([0, 0, 0, 1])) == pytest.approx(0.0)
    assert metrics.ece(p, np.array([1, 1, 1, 1])) == pytest.approx(0.75)


def test_reliability_bins_cover_every_case():
    p = np.array([[0.95, 0.05], [0.55, 0.45], [0.6, 0.4]])
    bins = metrics.reliability(p, np.array([0, 1, 0]), n_bins=10)
    assert sum(b["n"] for b in bins) == 3
    assert bins[9]["n"] == 1 and bins[9]["acc"] == 1.0


def test_risk_coverage_drops_risk_when_keeping_confident_cases():
    conf = np.array([0.9, 0.8, 0.7, 0.6])
    correct = np.array([True, True, False, False])
    rc = metrics.risk_coverage(conf, correct, n_points=4)
    assert [r["coverage"] for r in rc] == [0.25, 0.5, 0.75, 1.0]
    assert [r["risk"] for r in rc] == pytest.approx([0, 0, 1 / 3, 0.5])


def test_top_confusions_largest_off_diagonal_first():
    cm = np.array([[5, 3, 0], [1, 4, 0], [0, 2, 6]])
    assert metrics.top_confusions(cm, 2) == [(0, 1, 3), (2, 1, 2)]


def test_model_scores_macro_f1_and_recall_on_12_classes():
    y = np.array([0, 0, 1, 1])
    pred = np.array([0, 0, 1, 0])
    raptor = np.array(["No-Anomaly", "No-Anomaly", "Cell", "Hot-Spot"])
    s = evaluate.model_scores("x", y, pred, raptor)
    assert s["accuracy"] == 0.75
    assert s["recall_12"] == {"Cell": 1.0, "Hot-Spot": 0.0, "No-Anomaly": 1.0}
    assert s["macro_f1"] == pytest.approx((0.8 + 2 / 3) / 8)  # 6 classes never seen → 0


def test_selective_applies_the_unsure_rule():
    p = np.zeros((3, 8))
    p[0, 0] = 1.0  # confident ok, passes
    p[1, [0, 1]] = [0.5, 0.5]  # ok with 0.5 on a risk class → unsure
    p[2, 3] = 1.0  # confident diode, passes, but wrong
    s = evaluate.selective(p, np.array([0, 0, 0]), {**DEFAULT_THRESHOLDS, "groups": {
        "all": {"classes": evaluate.CLASSES, "target_precision": 0.95}}})
    assert s["coverage"] == pytest.approx(2 / 3)
    assert s["precision_auto"] == 0.5
    assert s["per_class"]["diode_substring"] == {"auto": 1, "precision": 0.0}


def test_errors_pick_the_most_confident_wrong_crops():
    crop = sorted((ROOT / "backend" / "tests" / "fixtures" / "crops").glob("*.jpg"))[0]
    rows = [{"image_id": str(i), "path": str(crop.relative_to(ROOT))} for i in range(3)]
    p = np.zeros((3, 8))
    p[0, 0], p[1, 4], p[2, 4] = 1.0, 0.6, 0.9
    out = evaluate.errors(p, np.array([0, 0, 0]), rows)
    assert out[0]["truth"] == "ok" and out[0]["pred"] == "module_offline" and out[0]["count"] == 2
    assert [e["image_id"] for e in out[0]["examples"]] == ["2", "1"]
    assert out[0]["examples"][0]["crop_png"].startswith("data:image/png;base64,")
