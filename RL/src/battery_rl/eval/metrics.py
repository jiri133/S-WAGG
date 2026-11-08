"""Per-day metrics for the merchant PV + battery site.

The metric names are frozen in ``TEAM_PLAN.md`` section 3.4.  Values are computed from the
environment's per-step ``info`` records under the merchant balance:

- ``import_cost_ron`` is the cost of grid charging;
- ``export_revenue_ron`` is PV plus battery-discharge revenue;
- ``net_cost_ron`` = import cost − export revenue (positive = spent, negative = earned);
- the site has zero local demand.

The LLM telemetry metrics are ``None`` for non-LLM strategies.  Build :class:`LLMTelemetry`
from the agent's decision log when evaluating the LLM.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from battery_rl.env.battery import DEFAULT_STEP_HOURS, BatterySpec

MetricValue = float | int | None

METRIC_NAMES: tuple[str, ...] = (
    "net_cost_ron",
    "import_cost_ron",
    "export_revenue_ron",
    "renewable_utilization",
    "self_consumption_ratio",
    "wasted_mwh",
    "throughput_mwh",
    "equivalent_cycles",
    "degradation_ron",
    "violations_mwh",
    "grid_import_mwh",
    "grid_export_mwh",
    "soc_min",
    "soc_max",
    "soc_end",
    "llm_feasible_rate",
    "llm_invalid_rate",
    "llm_tool_calls",
    "llm_tokens",
    "llm_latency_s",
    "llm_cost_ron",
)
"""The frozen per-day metric names, in contract order."""


@dataclass(frozen=True)
class LLMTelemetry:
    """Per-day LLM usage summary, built by the agent lane from its decision transcripts."""

    decisions: int = 0
    feasible: int = 0
    invalid: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    cost_ron: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "decisions",
            "feasible",
            "invalid",
            "tool_calls",
            "input_tokens",
            "output_tokens",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")
        if self.feasible > self.decisions:
            raise ValueError("feasible decisions cannot exceed decisions")
        if self.invalid > self.decisions:
            raise ValueError("invalid outputs cannot exceed decisions")
        if not math.isfinite(self.latency_s) or self.latency_s < 0:
            raise ValueError(f"latency_s must be finite and non-negative, got {self.latency_s}")
        if not math.isfinite(self.cost_ron) or self.cost_ron < 0:
            raise ValueError(f"cost_ron must be finite and non-negative, got {self.cost_ron}")


def compute_day_metrics(
    records: Sequence[Mapping[str, Any]],
    spec: BatterySpec,
    *,
    llm: LLMTelemetry | None = None,
    initial_soc: float | None = None,
    dt_h: float = DEFAULT_STEP_HOURS,
) -> dict[str, MetricValue]:
    """Compute the frozen per-day metrics from ``env.records``.

    ``records`` is the sequence of ``info`` dicts from one episode.  ``initial_soc`` is
    only used when ``records`` is empty (for a zero-step diagnostic run).
    """
    if not math.isfinite(dt_h) or dt_h <= 0:
        raise ValueError(f"dt_h must be finite and positive, got {dt_h}")

    import_cost_ron = 0.0
    export_revenue_ron = 0.0
    grid_import_mwh = 0.0
    grid_export_mwh = 0.0
    available_pv_mwh = 0.0
    pv_to_battery_mwh = 0.0
    curtailed_mwh = 0.0
    throughput_mwh = 0.0
    degradation_ron = 0.0
    violations_mwh = 0.0
    soc_values: list[float] = []

    for record in records:
        pv_mw = float(record["pv_mw"])
        price = float(record["price_ron_mwh"])
        import_mw = float(record["import_mw"])
        export_mw = float(record["export_mw"])
        charge_mw = float(record["p_charge_mw"])
        discharge_mw = float(record["p_discharge_mw"])
        curtailed_mw = float(record["curtailed_mw"])

        import_cost_ron += price * import_mw * dt_h
        export_revenue_ron += price * export_mw * dt_h
        grid_import_mwh += import_mw * dt_h
        grid_export_mwh += export_mw * dt_h
        available_pv_mwh += max(pv_mw, 0.0) * dt_h
        # Merchant site: PV either charges the battery or is exported.  Charge above PV is
        # grid charging and does not count as self-consumption.
        pv_to_battery_mwh += min(max(charge_mw, 0.0), max(pv_mw, 0.0)) * dt_h
        curtailed_mwh += max(curtailed_mw, 0.0) * dt_h
        throughput_mwh += (
            max(charge_mw, 0.0) * dt_h * spec.eta_c
            + max(discharge_mw, 0.0) * dt_h / spec.eta_d
        )
        degradation_ron += float(record["degradation_ron"])
        violations_mwh += max(float(record["violation_mwh"]), 0.0)
        soc_values.extend((float(record["soc"]), float(record["soc_next"])))

    if not soc_values and initial_soc is not None:
        soc_values.append(float(initial_soc))

    if available_pv_mwh > 0.0:
        renewable_utilization = _clamp01(1.0 - curtailed_mwh / available_pv_mwh)
        self_consumption_ratio = _clamp01(pv_to_battery_mwh / available_pv_mwh)
    else:
        # No PV generated: nothing was curtailed or self-consumed.
        renewable_utilization = 1.0
        self_consumption_ratio = 0.0

    if llm is None:
        llm_feasible_rate: MetricValue = None
        llm_invalid_rate: MetricValue = None
        llm_tool_calls: MetricValue = None
        llm_tokens: MetricValue = None
        llm_latency_s: MetricValue = None
        llm_cost_ron: MetricValue = None
    else:
        llm_feasible_rate = _ratio(llm.feasible, llm.decisions)
        llm_invalid_rate = _ratio(llm.invalid, llm.decisions)
        llm_tool_calls = llm.tool_calls
        llm_tokens = llm.input_tokens + llm.output_tokens
        llm_latency_s = llm.latency_s
        llm_cost_ron = llm.cost_ron

    net_cost_ron = import_cost_ron - export_revenue_ron
    return {
        "net_cost_ron": net_cost_ron,
        "import_cost_ron": import_cost_ron,
        "export_revenue_ron": export_revenue_ron,
        "renewable_utilization": renewable_utilization,
        "self_consumption_ratio": self_consumption_ratio,
        "wasted_mwh": curtailed_mwh,
        "throughput_mwh": throughput_mwh,
        "equivalent_cycles": throughput_mwh / (2.0 * spec.capacity_mwh),
        "degradation_ron": degradation_ron,
        "violations_mwh": violations_mwh,
        "grid_import_mwh": grid_import_mwh,
        "grid_export_mwh": grid_export_mwh,
        "soc_min": min(soc_values) if soc_values else None,
        "soc_max": max(soc_values) if soc_values else None,
        "soc_end": float(records[-1]["soc_next"]) if records else initial_soc,
        "llm_feasible_rate": llm_feasible_rate,
        "llm_invalid_rate": llm_invalid_rate,
        "llm_tool_calls": llm_tool_calls,
        "llm_tokens": llm_tokens,
        "llm_latency_s": llm_latency_s,
        "llm_cost_ron": llm_cost_ron,
    }


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator
