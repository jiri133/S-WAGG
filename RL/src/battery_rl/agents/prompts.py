"""Versioned prompts for the dispatch LLM.

The system prompt is static and cache-friendly.  The user prompt is a compact
state block plus a CSV-like forecast table for the rest of the delivery day.

v2 keeps the merchant contract and 17-level action space but fixes three
economics errors observed on the v1 validation sample:

- PV charging was treated as free; it actually forgoes export revenue at the
  current price.
- The end-of-day terminal value was used as an intraday charging hurdle.
- The model required charge and discharge to fit inside one execution window.

It also tells the model not to re-fetch state/forecast data that is already in
the user prompt and enforces the simulator-call budget.

v3 asks the model to attach a 0–100 confidence to every submitted schedule so
the operator can see how sure it is about the plan.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..config import AgentConfig

PROMPT_VERSION = "v3"


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
grid site. The site has NO local load: PV and battery discharge are sold to
the grid, and grid energy is bought only to charge the battery. National load
is market context, never site demand.

Objective: maximize net cash flow over the delivery day:
export revenue - import cost - battery degradation - constraint violations,
plus the value of energy left at the end of the day (terminal_value_ron_per_mwh).

Dispatch economics (apply this to every interval):
- Positive battery power discharges/sells; negative charges/buys; zero holds.
- There is no export limit, so PV is never curtailed. PV is exported or used
  to charge the battery. Charging from PV is NOT free: every MWh charged
  forgoes export revenue at the current price. Whether the energy comes from
  PV or the grid, the opportunity cost of charging is the current price.
- Charging now to discharge later at price p_later is profitable only if
      p_later > p_now / (eta_c * eta_d)
                + degradation_cost_ron_per_mwh * (1 + 1 / eta_d).
  The spread must clear round-trip inefficiency and degradation. If it does
  not, hold.
- Discharging now forgoes the best later discharge price in the remaining day.
  Discharge when the current price is high relative to the remaining-day
  prices. Do not dump stored energy at a moderate price if a materially higher
  price is still ahead and the battery can wait.
- terminal_value_ron_per_mwh applies ONLY to SoC left at the end of the
  delivery day. It is not the value of energy during the day and it is not a
  hurdle for charging. Compare intraday decisions with remaining-day prices.
- The battery is a daily arbitrage asset: charge near the cheapest intervals
  and discharge near the most expensive intervals. Use the full usable SoC
  range when the spread justifies it. Aim to be near soc_max before the most
  expensive block of the day and near soc_min after it.
- Avoid low-margin chattering: cycling for a spread smaller than the costs
  above is worse than holding.

Action space: exactly {len(action_levels)} signed levels, expressed as a
fraction of P_max:
{_levels_text(action_levels)}

Planning:
- You are called every 4 hours. The execution window is the next 16 intervals;
  the forecast table covers the rest of the delivery day.
- Plan the rest of the delivery day as one arbitrage problem, but return a
  schedule only for the execution window. A charge in this window may be
  discharged in a later window; charge and discharge do not need to fit inside
  the execution window.
- Prices are known data. Do not forecast prices.
- PV and national-load forecasts are given. National load is context only.
- The state block and forecast table already contain the get_state and
  get_forecast data. Do not call those tools; use the provided values.
- Use simulate_schedule to test candidate schedules. Call it at most
  {config.max_simulator_calls} times; a fourth call is rejected. The simulator
  scores only the 16-interval execution window, so use the forecast table to
  judge later windows. After the third simulation, submit the best feasible
  candidate.
- submit_schedule with the final schedule and a confidence from 0 to 100.
- If you return JSON directly, use this exact shape:
  {{"schedule": [{{"interval": 0, "level": -0.5}}, ...],
    "rationale": "...", "confidence": 85}}
- confidence is how sure you are that the returned schedule is the best
  feasible plan for this window, in percent. Lower it when the forecast or
  the price spread is uncertain. It is shown to the operator.
- Every level must be exactly one of the allowed levels above.
- The schedule length must equal the execution window length.
- The site is merchant-only: no local demand, no retail load cost.
"""


def _price_summary(values: list[float], offset: int) -> str:
    if not values:
        return "n/a"
    low_index = min(range(len(values)), key=values.__getitem__)
    high_index = max(range(len(values)), key=values.__getitem__)
    mean = sum(values) / len(values)
    return (
        f"min={values[low_index]:.1f} at idx {offset + low_index}, "
        f"mean={mean:.1f}, max={values[high_index]:.1f} at idx {offset + high_index}"
    )


def _ranked_intervals(
    values: list[float], offset: int, count: int, *, reverse: bool
) -> str:
    if not values:
        return "n/a"
    order = sorted(range(len(values)), key=values.__getitem__, reverse=reverse)[:count]
    return ", ".join(f"{offset + index}:{values[index]:.1f}" for index in order)


def build_user_prompt(context: dict, execution_steps: int) -> str:
    battery = context.get("battery", {})
    market = context.get("market", {})
    pv = context.get("pv", {})
    load = context.get("load", {})
    farm = context.get("farm", {})
    step = int(context.get("step_index", 0))
    prices = [float(value) for value in market.get("prices_ron_mwh", [])]
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
            f"{prices[step + index]:.2f},"
            f"{float(pv_forecast[index]):.3f},"
            f"{float(load_forecast[index]):.3f}"
        )
    table = "\n".join(rows) if rows else "(forecast arrays unavailable)"
    previous = context.get("previous_plan", [])
    previous_text = ", ".join(str(value) for value in previous) if previous else "none"

    terminal = context.get("terminal_value", {})
    if isinstance(terminal, dict):
        terminal_price = terminal.get("price_ron_mwh")
        terminal_mode = terminal.get("mode")
    else:
        terminal_price = terminal
        terminal_mode = None

    eta_c = float(battery.get("eta_c") or 1.0)
    eta_d = float(battery.get("eta_d") or 1.0)
    round_trip = eta_c * eta_d
    degradation = battery.get("degradation_cost_ron_per_mwh")

    remaining_prices = prices[step:] if len(prices) > step else []
    window_prices = remaining_prices[:execution_steps]
    cheapest = _ranked_intervals(remaining_prices, 0, 4, reverse=False)
    priciest = _ranked_intervals(remaining_prices, 0, 4, reverse=True)

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
eta_c={eta_c} eta_d={eta_d} degradation_cost_ron_per_mwh={degradation}
round_trip_efficiency: {round_trip:.4f}
terminal_value_ron_per_mwh: {terminal_price} (end-of-day SoC only; mode={terminal_mode})
limits: {context.get('limits')}
previous_plan: {previous_text}
execution_price_summary: {_price_summary(window_prices, 0)}
remaining_price_summary: {_price_summary(remaining_prices, 0)}
cheapest_remaining_intervals: {cheapest}
most_expensive_remaining_intervals: {priciest}

Forecast table (CSV, one row per 15-minute interval; idx is the offset from now):
idx,time_utc,price_ron_mwh,pv_forecast_mw,load_forecast_mw
{table}

The first {execution_steps} rows are the execution window. Return exactly
{execution_steps} schedule entries, one per row in that window, as JSON or via
submit_schedule, and include your confidence (0-100) in the plan.
"""
