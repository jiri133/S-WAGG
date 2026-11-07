"""MPC baseline: every 4 hours solve the battery LP over the rest of the day.

The LP uses the known D-1 prices, the PV forecast and the same degradation/terminal terms
as the environment, then executes the first four hours (or the shorter DST block) after
quantizing the continuous solution to the 17 action levels.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from battery_rl.agents.schemas import index_to_level
from battery_rl.env.battery import DEFAULT_STEP_HOURS, Battery, BatterySpec
from battery_rl.strategies.common import (
    HOLD_ACTION,
    charge_action,
    discharge_action,
    spec_from_context,
)
from battery_rl.strategies.lp import LPSolution, solve_battery_lp


class MPC:
    """Receding-horizon LP planner over the rest of the delivery day."""

    name = "mpc"

    def __init__(self, *, dt_h: float = DEFAULT_STEP_HOURS) -> None:
        self.dt_h = dt_h

    def plan(self, context: dict, execution_steps: int = 16) -> list[int]:
        step_index = int(context["step_index"])
        steps_remaining = int(context["steps_remaining"])
        if not 1 <= execution_steps <= steps_remaining:
            raise ValueError(
                f"execution_steps must be in 1..{steps_remaining}, got {execution_steps}"
            )
        all_prices = context["market"]["prices_ron_mwh"]
        prices = all_prices[step_index : step_index + steps_remaining]
        if len(prices) != steps_remaining:
            raise ValueError(
                f"price window has {len(prices)} entries, expected {steps_remaining}"
            )
        pv_forecast = context["pv"]["forecast_mw"]
        return plan_from_lp(
            context,
            execution_steps,
            prices,
            pv_forecast,
            dt_h=self.dt_h,
        )


def plan_from_lp(
    context: dict[str, Any],
    execution_steps: int,
    prices: Sequence[float],
    pv_mw: Sequence[float],
    *,
    dt_h: float = DEFAULT_STEP_HOURS,
) -> list[int]:
    """Solve the LP and return the feasible quantized actions for the execution window."""
    expected_execution = int(context["execution_steps"])
    if execution_steps != expected_execution:
        raise ValueError(
            f"execution_steps must equal context.execution_steps={expected_execution}, "
            f"got {execution_steps}"
        )
    steps_remaining = int(context["steps_remaining"])
    if len(prices) != steps_remaining:
        raise ValueError(
            f"prices must cover steps_remaining={steps_remaining}, got {len(prices)}"
        )
    if len(pv_mw) != steps_remaining:
        raise ValueError(
            f"pv_mw must cover steps_remaining={steps_remaining}, got {len(pv_mw)}"
        )

    spec = spec_from_context(context)
    terminal = context["terminal_value"]
    terminal_price = (
        None if terminal["mode"] == "none" else float(terminal["price_ron_mwh"])
    )
    start_soc = float(context["battery"]["soc"])
    solution = solve_battery_lp(
        prices,
        pv_mw,
        spec,
        start_soc=start_soc,
        degradation_cost_ron_per_mwh=float(
            context["battery"]["degradation_cost_ron_per_mwh"]
        ),
        terminal_price_ron_mwh=terminal_price,
        dt_h=dt_h,
    )
    return quantize_execution(solution, spec, execution_steps, start_soc, dt_h=dt_h)


def quantize_execution(
    solution: LPSolution,
    spec: BatterySpec,
    execution_steps: int,
    start_soc: float,
    *,
    dt_h: float = DEFAULT_STEP_HOURS,
) -> list[int]:
    """Quantize the LP solution to feasible action indices for the executed window.

    The quantization floors the requested power to the nearest action level in the
    direction of the LP's sign, then checks the actual SoC headroom, so every returned
    action is executable without clipping.
    """
    battery = Battery(spec, soc=start_soc)
    actions: list[int] = []
    for offset in range(execution_steps):
        desired_mw = float(solution.discharge_mw[offset] - solution.charge_mw[offset])
        if desired_mw > 1e-12:
            max_fraction = min(desired_mw / spec.p_max_mw, 1.0)
            action = discharge_action(
                spec, battery.soc, max_fraction=max_fraction, dt_h=dt_h
            )
        elif desired_mw < -1e-12:
            max_fraction = min(-desired_mw / spec.p_max_mw, 1.0)
            action = charge_action(spec, battery.soc, max_fraction=max_fraction, dt_h=dt_h)
        else:
            action = HOLD_ACTION
        actions.append(action)
        battery.step(index_to_level(action) * spec.p_max_mw, dt_h)
    return actions


__all__ = ["MPC", "plan_from_lp", "quantize_execution"]
