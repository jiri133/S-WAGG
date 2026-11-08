"""Simulator adapter for the LLM ``simulate_schedule`` tool (A-owned).

It replays a candidate schedule against the frozen context using lane B's
battery and balance primitives.  The context's forecast PV and known prices are
used, so the tool answers "what would this plan cost under the information the
agent has?"; the environment executes the realized values.

The environment itself is not mutated: each call starts from the context's SoC
and keeps its own battery state.
"""

from __future__ import annotations

from typing import Any

from battery_rl.agents.schemas import index_to_level
from battery_rl.env.balance import solve_balance
from battery_rl.env.battery import DEFAULT_STEP_HOURS, Battery, BatterySpec


class ContextSimulator:
    """Deterministic simulator implementing the ``agents.tools.Simulator`` protocol."""

    def __init__(
        self,
        *,
        dt_h: float = DEFAULT_STEP_HOURS,
        violation_penalty_ron_per_mwh: float = 0.0,
    ):
        if dt_h <= 0:
            raise ValueError(f"dt_h must be positive, got {dt_h}")
        if violation_penalty_ron_per_mwh < 0:
            raise ValueError("violation_penalty_ron_per_mwh must be non-negative")
        self.dt_h = dt_h
        self.violation_penalty_ron_per_mwh = violation_penalty_ron_per_mwh

    def simulate(
        self, context: dict, actions: list[int], execution_steps: int
    ) -> dict[str, Any]:
        if execution_steps < 1:
            raise ValueError(f"execution_steps must be at least 1, got {execution_steps}")
        if len(actions) != execution_steps:
            raise ValueError(
                f"actions has {len(actions)} entries, expected {execution_steps}"
            )

        battery_context = context["battery"]
        spec = BatterySpec(
            capacity_mwh=float(battery_context["capacity_mwh"]),
            p_max_mw=float(battery_context["p_max_mw"]),
            soc_min=float(battery_context["soc_min"]),
            soc_max=float(battery_context["soc_max"]),
            eta_c=float(battery_context["eta_c"]),
            eta_d=float(battery_context["eta_d"]),
        )
        battery = Battery(spec, soc=float(battery_context["soc"]))
        pv_forecast = [float(value) for value in context["pv"]["forecast_mw"]]
        prices = context["market"]["prices_ron_mwh"]
        step_index = int(context["step_index"])
        limits = context.get("limits", {})
        export_limit = limits.get("export_limit_mw")
        import_limit = limits.get("import_limit_mw")
        degradation_cost = float(
            battery_context.get("degradation_cost_ron_per_mwh", 0.0)
        )

        if execution_steps > len(pv_forecast):
            raise ValueError("context PV forecast does not cover the execution window")
        if step_index + execution_steps > len(prices):
            raise ValueError("context prices do not cover the execution window")

        import_cost = 0.0
        export_revenue = 0.0
        degradation_ron = 0.0
        violations_mwh = 0.0
        curtailed_mwh = 0.0
        soc_trajectory: list[float] = []
        feasible = True

        for offset in range(execution_steps):
            level = index_to_level(int(actions[offset]))
            battery_step = battery.step(level * spec.p_max_mw, self.dt_h)
            price = float(prices[step_index + offset])
            balance = solve_balance(
                pv_mw=pv_forecast[offset],
                demand_mw=0.0,
                price_ron_mwh=price,
                battery_mw=battery_step.executed_mw,
                dt_h=self.dt_h,
                export_limit_mw=export_limit,
                import_limit_mw=import_limit,
            )
            import_cost += price * balance.import_mw * self.dt_h
            export_revenue += price * balance.export_mw * self.dt_h
            degradation_ron += degradation_cost * battery_step.throughput_mwh
            violations_mwh += battery_step.violation_mwh
            curtailed_mwh += balance.curtailed_mw * self.dt_h
            soc_trajectory.append(battery_step.soc_after)
            feasible = feasible and battery_step.feasible

        violation_penalty_ron = (
            self.violation_penalty_ron_per_mwh * violations_mwh
        )
        net_cost_ron = import_cost - export_revenue
        return {
            "net_cost_ron": net_cost_ron,
            "import_cost_ron": import_cost,
            "export_revenue_ron": export_revenue,
            "degradation_ron": degradation_ron,
            "violation_penalty_ron": violation_penalty_ron,
            "score_ron": -net_cost_ron - degradation_ron - violation_penalty_ron,
            "violations_mwh": violations_mwh,
            "curtailed_mwh": curtailed_mwh,
            "soc_trajectory": soc_trajectory,
            "feasible": feasible,
        }
