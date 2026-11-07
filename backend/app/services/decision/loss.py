"""Production loss per finding from config/loss.yaml + PVGIS yield (DESIGN_SPEC §7)."""

import json
from functools import lru_cache

import yaml

from app.services.decision.rules import CONFIG_DIR


@lru_cache
def load_loss() -> dict:
    return yaml.safe_load((CONFIG_DIR / "loss.yaml").read_text(encoding="utf-8"))


@lru_cache
def daily_yield() -> dict[int, float]:
    """Month (1–12) → kWh/kWp/day, from the saved PVGIS response."""
    pvgis = json.loads((CONFIG_DIR / "pvgis_bucharest.json").read_text(encoding="utf-8"))
    return {m["month"]: m["E_d"] for m in pvgis["outputs"]["monthly"]["fixed"]}


def loss_kwh_day(cls: str, month: int) -> float:
    cfg = load_loss()
    return round(cfg["module_kwp"] * cfg["fractions"][cls] * daily_yield()[month], 3)


def loss_ron_day(kwh_day: float) -> float:
    return round(kwh_day * load_loss()["price_ron_per_kwh"], 2)
