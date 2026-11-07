"""Build the versioned agent context JSON from the environment and farm config.

The shape is frozen in ``TEAM_PLAN.md`` section 3.2 and validated by
``agents.schemas.AgentContext``.  Causality rules:

- ``pv.realized_so_far_mw`` contains only actual PV **before** the decision interval;
- ``pv.now_mw`` and ``pv.forecast_mw`` come from the forecast column, never from future
  actuals;
- ``load.now_mw`` and ``load.forecast_mw`` are national **market context** (day-ahead
  forecast), never the site demand;
- ``market.prices_ron_mwh`` is the whole delivery day, known one day ahead.
"""

from __future__ import annotations

from collections.abc import Sequence

from battery_rl.agents.schemas import (
    EXECUTION_STEPS,
    AgentContext,
    BatteryContext,
    FarmContext,
    LimitsContext,
    LoadContext,
    MarketContext,
    PVContext,
    TerminalValue,
)
from battery_rl.config import FarmConfig
from battery_rl.env.env import BatteryEnv


def build_context(
    env: BatteryEnv,
    farm: FarmConfig,
    *,
    previous_plan: Sequence[int] | None = None,
) -> AgentContext:
    """Build the validated context at the environment's current decision point.

    ``previous_plan`` holds action indices from the previous decision; pass the runner's
    last plan, or omit it at the first decision of the day.
    """
    day = env.day
    if day is None:
        raise RuntimeError("call env.reset() before building a context")
    if env.done:
        raise RuntimeError("cannot build a context after the episode is complete")

    step_index = env.step_index
    steps_remaining = env.steps_remaining
    execution_steps = min(EXECUTION_STEPS, steps_remaining)
    if execution_steps <= 0:
        raise RuntimeError("no intervals remaining in this delivery day")

    prices = [float(value) for value in day.price_ron_mwh]
    pv_forecast = [float(value) for value in day.pv_forecast_mw[step_index:]]
    pv_realized = [float(value) for value in day.pv_mw[:step_index]]
    load_forecast = [float(value) for value in day.load_forecast_mw[step_index:]]

    return AgentContext(
        delivery_day=day.day,
        farm=FarmContext(
            name=farm.name,
            lat=farm.latitude,
            lon=farm.longitude,
            kwp=farm.pv.kwp,
            asset_scale=farm.asset_scale,
        ),
        time_utc=env.current_time_utc,
        step_index=step_index,
        steps_remaining=steps_remaining,
        execution_steps=execution_steps,
        battery=BatteryContext(
            capacity_mwh=env.spec.capacity_mwh,
            p_max_mw=env.spec.p_max_mw,
            soc=env.soc,
            soc_min=env.spec.soc_min,
            soc_max=env.spec.soc_max,
            eta_c=env.spec.eta_c,
            eta_d=env.spec.eta_d,
            degradation_cost_ron_per_mwh=env.objective.degradation_cost_ron_per_mwh,
        ),
        market=MarketContext(currency="RON", prices_ron_mwh=prices),
        pv=PVContext(
            now_mw=float(day.pv_forecast_mw[step_index]),
            forecast_mw=pv_forecast,
            realized_so_far_mw=pv_realized,
        ),
        load=LoadContext(
            now_mw=float(day.load_forecast_mw[step_index]),
            forecast_mw=load_forecast,
        ),
        limits=LimitsContext(
            export_limit_mw=farm.grid.export_limit_mw,
            import_limit_mw=farm.grid.import_limit_mw,
        ),
        terminal_value=TerminalValue(
            price_ron_mwh=env.terminal_price_ron_mwh,
            mode=env.objective.terminal_value_mode,
        ),
        previous_plan=list(previous_plan) if previous_plan is not None else [],
    )


def build_context_dict(
    env: BatteryEnv,
    farm: FarmConfig,
    *,
    previous_plan: Sequence[int] | None = None,
) -> dict:
    """JSON-safe context payload for ``Planner.plan`` and the LLM prompt."""
    return build_context(env, farm, previous_plan=previous_plan).model_dump(mode="json")
