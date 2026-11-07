"""Explicit decision rules from config/decision_rules.yaml (DESIGN_SPEC §7)."""

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


@lru_cache
def load_rules() -> dict:
    return yaml.safe_load((CONFIG_DIR / "decision_rules.yaml").read_text(encoding="utf-8"))


def apply(cls: str, delta_t_k: float) -> dict:
    """Class + apparent ΔT → urgency, alert flag, crew, part, hours and the quoted rule."""
    rules = load_rules()
    per_class = rules["classes"][cls]
    safety = rules["safety"]
    if cls in safety["classes"] and delta_t_k >= safety["delta_t_min_k"]:
        urgency, alert = safety["urgency"], safety["alert"]
        rule = (
            f"decision_rules.yaml › safety: {cls} cu ΔT {delta_t_k:.1f} K "
            f"≥ {safety['delta_t_min_k']} K → {urgency} + alertă"
        )
    else:
        urgency, alert = per_class["urgency"], False
        rule = f"decision_rules.yaml › classes.{cls}: urgență de bază {urgency}"
    return {
        "urgency": urgency,
        "alert": alert,
        "crew": per_class["crew"],
        "part": per_class["part"],
        "est_hours": per_class["est_hours"],
        "rule_applied": f"{rule} · verificare: {per_class['check']}",
    }


def score(urgency: str, loss_kwh_day: float) -> float:
    return round(load_rules()["urgency_weights"][urgency] * loss_kwh_day, 3)
