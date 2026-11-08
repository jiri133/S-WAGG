"""Per-day metric contract: merchant costs, energy, SoC and LLM telemetry."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from battery_rl.config import load_env_config, load_farm_config
from battery_rl.data.dataset import load_days
from battery_rl.env.battery import BatterySpec
from battery_rl.env.env import BatteryEnv
from battery_rl.eval.metrics import (
    METRIC_NAMES,
    LLMTelemetry,
    compute_day_metrics,
)
from battery_rl.seeding import make_rng

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"
SPEC = BatterySpec(capacity_mwh=10.0, p_max_mw=2.0)

EXPECTED_METRICS = (
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


def record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "timestamp_utc": "2026-01-15T00:00:00Z",
        "step_index": 0,
        "pv_mw": 0.0,
        "load_mw": 5000.0,  # market context, never a balance demand
        "price_ron_mwh": 100.0,
        "soc": 0.5,
        "soc_next": 0.5475,
        "p_charge_mw": 2.0,
        "p_discharge_mw": 0.0,
        "requested_level": -1.0,
        "executed_level": -1.0,
        "import_mw": 2.0,
        "export_mw": 0.0,
        "curtailed_mw": 0.0,
        "cost_ron": 50.0,
        "degradation_ron": 23.75,
        "violation_mwh": 0.0,
        "feasible": True,
    }
    base.update(overrides)
    return base


def test_metric_names_are_the_frozen_contract() -> None:
    assert METRIC_NAMES == EXPECTED_METRICS


def test_hand_computed_charge_then_discharge_day() -> None:
    records = [
        record(),
        record(
            step_index=1,
            price_ron_mwh=500.0,
            soc=0.5475,
            soc_next=0.4948684210526316,
            p_charge_mw=0.0,
            p_discharge_mw=2.0,
            requested_level=1.0,
            executed_level=1.0,
            import_mw=0.0,
            export_mw=2.0,
            cost_ron=-250.0,
            degradation_ron=26.31578947368421,
        ),
    ]
    metrics = compute_day_metrics(records, SPEC)

    assert metrics["import_cost_ron"] == pytest.approx(50.0)
    assert metrics["export_revenue_ron"] == pytest.approx(250.0)
    assert metrics["net_cost_ron"] == pytest.approx(-200.0)
    assert metrics["grid_import_mwh"] == pytest.approx(0.5)
    assert metrics["grid_export_mwh"] == pytest.approx(0.5)
    assert metrics["throughput_mwh"] == pytest.approx(0.475 + 0.5263157894736842)
    assert metrics["equivalent_cycles"] == pytest.approx(
        (0.475 + 0.5263157894736842) / (2.0 * 10.0)
    )
    assert metrics["degradation_ron"] == pytest.approx(50.06578947368421)
    assert metrics["violations_mwh"] == pytest.approx(0.0)
    assert metrics["soc_min"] == pytest.approx(0.4948684210526316)
    assert metrics["soc_max"] == pytest.approx(0.5475)
    assert metrics["soc_end"] == pytest.approx(0.4948684210526316)

    # No PV: nothing to curtail or self-consume.
    assert metrics["renewable_utilization"] == pytest.approx(1.0)
    assert metrics["self_consumption_ratio"] == pytest.approx(0.0)
    assert metrics["wasted_mwh"] == pytest.approx(0.0)


def test_pv_retained_in_the_battery_counts_as_self_consumption() -> None:
    metrics = compute_day_metrics(
        [
            record(
                pv_mw=4.0,
                p_charge_mw=1.0,
                p_discharge_mw=0.0,
                soc=0.5,
                soc_next=0.52375,
                import_mw=0.0,
                export_mw=3.0,
                price_ron_mwh=100.0,
                cost_ron=-75.0,
                degradation_ron=11.875,
            )
        ],
        SPEC,
    )
    assert metrics["grid_import_mwh"] == pytest.approx(0.0)
    assert metrics["grid_export_mwh"] == pytest.approx(0.75)
    assert metrics["throughput_mwh"] == pytest.approx(0.2375)
    assert metrics["degradation_ron"] == pytest.approx(11.875)
    # 1 MW of 4 MW charges the battery for one interval: 0.25 MWh of 1.0 MWh PV.
    assert metrics["self_consumption_ratio"] == pytest.approx(0.25)
    assert metrics["renewable_utilization"] == pytest.approx(1.0)
    assert metrics["wasted_mwh"] == pytest.approx(0.0)
    assert metrics["net_cost_ron"] == pytest.approx(-75.0)


def test_curtailment_reduces_renewable_utilization() -> None:
    metrics = compute_day_metrics(
        [
            record(
                pv_mw=4.0,
                p_charge_mw=0.0,
                p_discharge_mw=0.0,
                soc=0.5,
                soc_next=0.5,
                import_mw=0.0,
                export_mw=2.0,
                curtailed_mw=2.0,
                cost_ron=-50.0,
                degradation_ron=0.0,
            )
        ],
        SPEC,
    )
    assert metrics["wasted_mwh"] == pytest.approx(0.5)
    assert metrics["renewable_utilization"] == pytest.approx(0.5)
    assert metrics["self_consumption_ratio"] == pytest.approx(0.0)
    assert metrics["grid_export_mwh"] == pytest.approx(0.5)


def test_llm_telemetry_metrics() -> None:
    llm = LLMTelemetry(
        decisions=6,
        feasible=5,
        invalid=1,
        tool_calls=9,
        input_tokens=3000,
        output_tokens=600,
        latency_s=12.5,
        cost_ron=0.4,
    )
    metrics = compute_day_metrics([], SPEC, llm=llm, initial_soc=0.5)
    assert metrics["llm_feasible_rate"] == pytest.approx(5 / 6)
    assert metrics["llm_invalid_rate"] == pytest.approx(1 / 6)
    assert metrics["llm_tool_calls"] == 9
    assert metrics["llm_tokens"] == 3600
    assert metrics["llm_latency_s"] == pytest.approx(12.5)
    assert metrics["llm_cost_ron"] == pytest.approx(0.4)
    assert metrics["net_cost_ron"] == pytest.approx(0.0)
    assert metrics["soc_min"] == pytest.approx(0.5)
    assert metrics["soc_max"] == pytest.approx(0.5)
    assert metrics["soc_end"] == pytest.approx(0.5)


def test_llm_metrics_are_none_for_non_llm_runs() -> None:
    metrics = compute_day_metrics([record()], SPEC)
    for name in (
        "llm_feasible_rate",
        "llm_invalid_rate",
        "llm_tool_calls",
        "llm_tokens",
        "llm_latency_s",
        "llm_cost_ron",
    ):
        assert metrics[name] is None


def test_empty_records_without_initial_soc_have_no_soc_metrics() -> None:
    metrics = compute_day_metrics([], SPEC)
    assert metrics["soc_min"] is None
    assert metrics["soc_max"] is None
    assert metrics["soc_end"] is None


def test_llm_telemetry_validates_its_fields() -> None:
    with pytest.raises(ValueError, match="decisions"):
        LLMTelemetry(decisions=-1)
    with pytest.raises(ValueError, match="feasible"):
        LLMTelemetry(decisions=2, feasible=3)
    with pytest.raises(ValueError, match="invalid"):
        LLMTelemetry(decisions=2, invalid=3)
    with pytest.raises(ValueError, match="latency_s"):
        LLMTelemetry(latency_s=-1.0)
    with pytest.raises(ValueError, match="cost_ron"):
        LLMTelemetry(cost_ron=-1.0)


def test_metrics_match_environment_totals_over_a_real_day() -> None:
    day = load_days(FIXTURES / "tiny_day.csv")[date(2026, 1, 15)]
    env = BatteryEnv.from_farm(day, load_farm_config(), load_env_config())
    env.reset()
    rng = make_rng(5)
    for _ in range(day.intervals):
        env.step(int(rng.integers(0, 17)))

    metrics = compute_day_metrics(env.records, env.spec)
    assert metrics["net_cost_ron"] == pytest.approx(env.total_cost_ron)
    assert metrics["degradation_ron"] == pytest.approx(env.total_degradation_ron)
    assert metrics["violations_mwh"] == pytest.approx(
        sum(record["violation_mwh"] for record in env.records)
    )
    assert metrics["grid_import_mwh"] == pytest.approx(
        sum(record["import_mw"] * 0.25 for record in env.records)
    )
    assert metrics["grid_export_mwh"] == pytest.approx(
        sum(record["export_mw"] * 0.25 for record in env.records)
    )
    assert metrics["soc_end"] == pytest.approx(env.soc)
    assert metrics["equivalent_cycles"] == pytest.approx(
        metrics["throughput_mwh"] / (2.0 * env.spec.capacity_mwh)
    )
    assert 0.1 - 1e-9 <= metrics["soc_min"] <= metrics["soc_max"] <= 0.9 + 1e-9
