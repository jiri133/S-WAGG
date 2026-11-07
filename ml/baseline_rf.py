"""Baseline B: Random Forest on the same intensity features as the rules.

Trained on train, scored on val next to the tuned rules (Baseline A).
Test is never read here (it is for evaluate.py, which can call train_rf()).

    uv run --project ml python ml/baseline_rf.py
"""

from sklearn.ensemble import RandomForestClassifier

from tune_rules import load_thresholds, predict, report, split_features


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


def main() -> None:
    X, y = split_features("train")
    Xv, yv = split_features("val")
    report("rules", yv, predict(Xv, load_thresholds()))
    report("random_forest", yv, train_rf(X, y).predict(Xv))


if __name__ == "__main__":
    main()
