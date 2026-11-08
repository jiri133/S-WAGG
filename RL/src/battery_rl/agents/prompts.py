"""Versioned prompts for the dispatch LLM.

The system prompt is static and cache-friendly.  The user prompt is a compact
state block plus a CSV-like forecast table for the rest of the delivery day.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..config import AgentConfig

PROMPT_VERSION = "v1"


def _levels_text(levels: list[float]) -> str:
    return ", ".join(f"{level:g}" for level in levels)


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def build_system_prompt(config: AgentConfig, action_levels: list[float]) -> str:
    return f"""You are a battery dispatch operator for a merchant PV + battery +
grid site. The site has NO local load. It sells PV and battery discharge to the
grid and buys grid energy only to charge the battery. National load is market
context, not site demand.

Objective: maximize net cash flow = export revenue - grid charging cost -
battery degradation - constraint violations, plus the terminal SoC value.

Assets and constraints:
- The battery capacity, power limit, SoC limits and efficiencies are in the user
  state block.
- The grid has no export limit unless the state block says otherwise.
- Positive battery power discharges/sells; negative charges/buys; zero holds.
- Grid charging is profitable only if the later price exceeds the current price
  divided by round-trip efficiency plus degradation.

Action space: exactly {len(action_levels)} signed levels, expressed as a
fraction of P_max:
{_levels_text(action_levels)}

Planning:
- Consider the rest of the delivery day, but return a schedule for the execution
  window requested in the user message.
- Prices are known data. Do not forecast prices.
- PV and national load forecasts are given. National load is context only.
- Use the tools:
  - get_state: current battery and site state.
  - get_forecast: remaining price, PV and national-load forecasts.
  - simulate_schedule: run a candidate schedule through the simulator; call it
    before submitting. At most {config.max_simulator_calls} simulator calls.
  - submit_schedule: final schedule.
- If you return JSON directly, use this exact shape:
  {{"schedule": [{{"interval": 0, "level": -0.5}}, ...], "rationale": "..."}}
- Every level must be exactly one of the allowed levels above.
- The schedule length must equal the execution window length.
- The site is merchant-only: no local demand, no retail load cost.
"""


def build_user_prompt(context: dict, execution_steps: int) -> str:
    battery = context.get("battery", {})
    market = context.get("market", {})
    pv = context.get("pv", {})
    load = context.get("load", {})
    farm = context.get("farm", {})
    step = int(context.get("step_index", 0))
    prices = list(market.get("prices_ron_mwh", []))
    pv_forecast = list(pv.get("forecast_mw", []))
    load_forecast = list(load.get("forecast_mw", []))
    start = _parse_time(context.get("time_utc"))

    available = min(
        len(prices) - step if len(prices) > step else 0,
        len(pv_forecast),
        len(load_forecast),
    )
    rows: list[str] = []
    for index in range(max(0, available)):
        stamp = start + timedelta(minutes=15 * index) if start else None
        rows.append(
            f"{index},{stamp.isoformat() if stamp else ''},"
            f"{float(prices[step + index]):.2f},"
            f"{float(pv_forecast[index]):.3f},"
            f"{float(load_forecast[index]):.3f}"
        )
    table = "\n".join(rows) if rows else "(forecast arrays unavailable)"
    previous = context.get("previous_plan", [])
    previous_text = ", ".join(str(value) for value in previous) if previous else "none"

    return f"""State:
delivery_day: {context.get('delivery_day')}
time_utc: {context.get('time_utc')}
step_index: {step}
steps_remaining: {context.get('steps_remaining')}
execution_steps: {execution_steps}
site_demand_mw: 0.0 (merchant)
farm: {farm.get('name')} | kwp={farm.get('kwp')} | asset_scale={farm.get('asset_scale')}
battery: capacity_mwh={battery.get('capacity_mwh')} p_max_mw={battery.get('p_max_mw')} \
soc={battery.get('soc')} soc_min={battery.get('soc_min')} soc_max={battery.get('soc_max')} \
eta_c={battery.get('eta_c')} eta_d={battery.get('eta_d')}
terminal_value: {context.get('terminal_value')}
limits: {context.get('limits')}
previous_plan: {previous_text}

Forecast table (CSV, one row per 15-minute interval):
idx,time_utc,price_ron_mwh,pv_forecast_mw,load_forecast_mw
{table}

The first {execution_steps} rows are the execution window. Return exactly
{execution_steps} schedule entries, one per row in that window, as JSON or via
submit_schedule.
"""
