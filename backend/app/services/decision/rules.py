"""Explicit decision rules from config/decision_rules.yaml (DESIGN_SPEC §7)."""

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


@lru_cache
def load_rules() -> dict:
    return yaml.safe_load((CONFIG_DIR / "decision_rules.yaml").read_text(encoding="utf-8"))


def urgency(cls: str, delta_t_k: float) -> tuple[str, bool, str]:
    """Class + apparent ΔT → urgency, alert flag and the quoted rule.

    The safety rule trips on ΔT alone, whatever class the model picked (ADR 0001).
    """
    rules = load_rules()
    safety = rules["safety"]
    if delta_t_k >= safety["delta_t_min_k"]:
        dt = f"{delta_t_k:.1f}".replace(".", ",")
        rule = (
            f"decision_rules.yaml › safety: ΔT {dt} K ≥ {safety['delta_t_min_k']} K "
            f"→ {safety['urgency']} + alertă, indiferent de model"
        )
        return safety["urgency"], safety["alert"], rule
    base = rules["classes"][cls]["urgency"]
    return base, False, f"urgență din {cls} (decision_rules.yaml › classes.{cls}: {base})"


def apply(cls: str, delta_t_k: float) -> dict:
    """Class + apparent ΔT → urgency, alert flag, the class's work content and the rule.

    When the safety rule trips the order goes to its crew (electricians), whatever the class.
    """
    per_class = load_rules()["classes"][cls]
    level, alert, rule = urgency(cls, delta_t_k)
    return {
        "urgency": level,
        "alert": alert,
        "crew": load_rules()["safety"]["crew"] if alert else per_class["crew"],
        "part": per_class["part"],
        "est_hours": per_class["est_hours"],
        "check": per_class["check"],
        "short": per_class["short"],
        "rule": rule,
    }


def weight(cls: str) -> float:
    """Urgency weight of the class's base urgency."""
    rules = load_rules()
    return rules["urgency_weights"][rules["classes"][cls]["urgency"]]
