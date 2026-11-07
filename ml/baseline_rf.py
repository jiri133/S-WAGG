"""Baseline B: Random Forest on the same intensity features as the rules.

Trained on train, scored on val next to the tuned rules (Baseline A).
Test is read only with --test, which evaluate.py calls once (sklearn stays out of the backend):
it writes {image_id: class} for ml/splits/test.csv to the given JSON file.

    uv run --project ml python ml/baseline_rf.py
    uv run --project ml python ml/baseline_rf.py --test reports/rf_test_pred.json
"""

import csv
import json
import sys

from sklearn.ensemble import RandomForestClassifier

from tune_rules import ROOT, load_thresholds, predict, report, split_features


def train_rf(X, y) -> RandomForestClassifier:
    """Balanced class weights, because soiling has 143 train crops against 7001 ok."""
    rf = RandomForestClassifier(
        n_estimators=500,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=42,
    )
    return rf.fit(X, y)


def write_test_predictions(out: str) -> None:
    X, y = split_features("train")
    Xt, _ = split_features("test")
    with open(ROOT / "ml" / "splits" / "test.csv", encoding="utf-8") as fh:
        ids = [r["image_id"] for r in csv.DictReader(fh)]
    pred = train_rf(X, y).predict(Xt)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(dict(zip(ids, map(str, pred), strict=True)), fh)


def main() -> None:
    if "--test" in sys.argv:
        write_test_predictions(sys.argv[sys.argv.index("--test") + 1])
        return
    X, y = split_features("train")
    Xv, yv = split_features("val")
    report("rules", yv, predict(Xv, load_thresholds()))
    report("random_forest", yv, train_rf(X, y).predict(Xv))


if __name__ == "__main__":
    main()
