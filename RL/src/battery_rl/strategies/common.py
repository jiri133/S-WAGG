"""Shared helpers for the merchant baselines and block planners (B-owned).

Actions are the 17 signed levels from ``agents.schemas``: index 0 is full charge, index 8
is hold, index 16 is full discharge.  The helpers quantize a desired power fraction to the
largest feasible level so a rule never requests more than the battery can deliver.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from battery_rl.agents.schemas import ACTION_COUNT, index_to_level
from battery_rl.env.battery import DEFAULT_STEP_HOURS, Battery, BatterySpec

HOLD_ACTION = 8
FULL_CHARGE_ACTION = 0
FULL_DISCHARGE_ACTION = 16
LEVEL_STEP = 0.125

ChooseAction = Callable[[Mapping[str, Any]], int]


def spec_from_context(context: Mapping[str, Any]) -> BatterySpec:
    """Rebuild the scaled battery spec from a context dict."""
    battery = context["battery"]
    return BatterySpec(
        capacity_mwh=float(battery["capacity_mwh"]),
        p_max_mw=float(battery["p_max_mw"]),
        soc_min=float(battery["soc_min"]),
        soc_max=float(battery["soc_max"]),
        eta_c=float(battery["eta_c"]),
        eta_d=float(battery["eta_d"]),
    )


def charge_action(
    spec: BatterySpec,
    soc: float,
    *,
    max_fraction: float = 1.0,
    deadband: float = 0.0,
    dt_h: float = DEFAULT_STEP_HOURS,
) -> int:
    """Largest charge level that does not exceed ``max_fraction`` or the SoC headroom."""
    if not 0.0 <= max_fraction <= 1.0:
        raise ValueError(f"max_fraction must be in [0, 1], got {max_fraction}")
    if soc >= spec.soc_max - deadband:
        return HOLD_ACTION
    headroom_mw = (spec.soc_max - soc) * spec.capacity_mwh / (spec.eta_c * dt_h)
    fraction = max(0.0, min(max_fraction, headroom_mw / spec.p_max_mw))
    steps = math.floor(fraction / LEVEL_STEP + 1e-9)
    return max(FULL_CHARGE_ACTION, HOLD_ACTION - steps)


def discharge_action(
    spec: BatterySpec,
    soc: float,
    *,
    max_fraction: float = 1.0,
    deadband: float = 0.0,
    dt_h: float = DEFAULT_STEP_HOURS,
) -> int:
    """Largest discharge level that does not exceed ``max_fraction`` or the SoC headroom."""
    if not 0.0 <= max_fraction <= 1.0:
        raise ValueError(f"max_fraction must be in [0, 1], got {max_fraction}")
    if soc <= spec.soc_min + deadband:
        return HOLD_ACTION
    headroom_mw = (soc - spec.soc_min) * spec.capacity_mwh * spec.eta_d / dt_h
    fraction = max(0.0, min(max_fraction, headroom_mw / spec.p_max_mw))
    steps = math.floor(fraction / LEVEL_STEP + 1e-9)
    return min(FULL_DISCHARGE_ACTION, HOLD_ACTION + steps)


def simulate_plan(
    context: Mapping[str, Any],
    choose_action: ChooseAction,
    execution_steps: int,
    *,
    dt_h: float = DEFAULT_STEP_HOURS,
) -> list[int]:
    """Build a feasible block plan by simulating the rule over the context window.

    ``choose_action`` receives a dict with the current ``soc``, the forecast ``pv_mw`` and
    the known ``price_ron_mwh``.  The battery is advanced with the same equations as the
    environment, so the returned action indices are feasible when executed.
    """
    if execution_steps < 1:
        raise ValueError(f"execution_steps must be at least 1, got {execution_steps}")
    spec = spec_from_context(context)
    pv_forecast = context["pv"]["forecast_mw"]
    prices = context["market"]["prices_ron_mwh"]
    step_index = int(context["step_index"])
    if len(pv_forecast) < execution_steps:
        raise ValueError(
            f"pv.forecast_mw has {len(pv_forecast)} entries, need {execution_steps}"
        )
    if step_index + execution_steps > len(prices):
        raise ValueError(
            "price window runs past the end of the delivery day: "
            f"step_index={step_index}, execution_steps={execution_steps}, "
            f"prices={len(prices)}"
        )

    battery = Battery(spec, soc=float(context["battery"]["soc"]))
    actions: list[int] = []
    for offset in range(execution_steps):
        info = {
            "soc": battery.soc,
            "pv_mw": float(pv_forecast[offset]),
            "price_ron_mwh": float(prices[step_index + offset]),
        }
        action = int(choose_action(info))
        if not 0 <= action < ACTION_COUNT:
            raise ValueError(f"choose_action returned an invalid index: {action}")
        actions.append(action)
        battery.step(index_to_level(action) * spec.p_max_mw, dt_h)
    return actions
