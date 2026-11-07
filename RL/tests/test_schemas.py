"""Contract tests for the frozen agent context, schedule and planner protocols.

These tests are the gate A codes against: if this file changes, the interface changed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from battery_rl.agents.base import Planner, StepStrategy
from battery_rl.agents.schemas import (
    ACTION_COUNT,
    ACTION_LEVELS,
    CONTEXT_VERSION,
    MAX_SOC_ERRORS,
    AgentContext,
    BatteryContext,
    Schedule,
    ScheduleValidationError,
    action_power_mw,
    index_to_level,
    level_to_index,
    parse_schedule,
    validate_schedule,
)
from battery_rl.config import load_env_config


def make_context(steps: int = 96, step_index: int = 48) -> dict[str, Any]:
    """A valid context payload with a full delivery day of ``steps`` intervals."""
    steps_remaining = steps - step_index
    execution_steps = min(16, steps_remaining)
    previous_plan = [] if step_index == 0 else [8] * execution_steps
    return {
        "context_version": CONTEXT_VERSION,
        "delivery_day": "2026-11-05",
        "farm": {
            "name": "seed",
            "lat": 44.4,
            "lon": 26.1,
            "kwp": 6000.0,
            "asset_scale": 1.0,
        },
        "time_utc": "2026-11-05T12:00:00Z",
        "step_index": step_index,
        "steps_remaining": steps_remaining,
        "execution_steps": execution_steps,
        "battery": {
            "capacity_mwh": 10.0,
            "p_max_mw": 2.0,
            "soc": 0.42,
            "soc_min": 0.10,
            "soc_max": 0.90,
            "eta_c": 0.95,
            "eta_d": 0.95,
            "degradation_cost_ron_per_mwh": 50.0,
        },
        "market": {"currency": "RON", "prices_ron_mwh": [500.0] * steps},
        "pv": {
            "now_mw": 3.1,
            "forecast_mw": [2.0] * steps_remaining,
            "realized_so_far_mw": [1.0] * step_index,
        },
        "load": {"now_mw": 5788.0, "forecast_mw": [5700.0] * steps_remaining},
        "limits": {"export_limit_mw": None, "import_limit_mw": None},
        "terminal_value": {"price_ron_mwh": 735.0, "mode": "episode_mean_price"},
        "previous_plan": previous_plan,
    }


# ---------------------------------------------------------------------------
# Action space
# ---------------------------------------------------------------------------


def test_action_levels_match_env_config() -> None:
    env = load_env_config()
    assert list(ACTION_LEVELS) == env.action_levels
    assert len(ACTION_LEVELS) == ACTION_COUNT == 17


def test_action_levels_span_signed_range() -> None:
    assert ACTION_LEVELS[0] == -1.0
    assert ACTION_LEVELS[-1] == 1.0
    assert 0.0 in ACTION_LEVELS
    assert all(
        later > earlier
        for earlier, later in zip(ACTION_LEVELS, ACTION_LEVELS[1:], strict=False)
    )


def test_index_level_round_trip() -> None:
    for index in range(ACTION_COUNT):
        assert level_to_index(index_to_level(index)) == index


def test_action_index_bounds() -> None:
    with pytest.raises(ValueError, match="action index"):
        index_to_level(-1)
    with pytest.raises(ValueError, match="action index"):
        index_to_level(ACTION_COUNT)
    with pytest.raises(ValueError, match="signed levels"):
        level_to_index(0.1)


def test_action_power_is_level_times_p_max() -> None:
    assert action_power_mw(16, 2.0) == pytest.approx(2.0)
    assert action_power_mw(0, 2.0) == pytest.approx(-2.0)
    assert action_power_mw(8, 2.0) == pytest.approx(0.0)
    with pytest.raises(ValueError, match="p_max_mw"):
        action_power_mw(8, 0.0)


# ---------------------------------------------------------------------------
# Context contract
# ---------------------------------------------------------------------------


def test_valid_context_round_trips() -> None:
    payload = make_context()
    context = AgentContext.model_validate(payload)
    dumped = context.model_dump(mode="json")
    assert dumped["context_version"] == "1"
    assert dumped["delivery_day"] == "2026-11-05"
    assert AgentContext.model_validate(dumped) == context


def test_context_version_is_frozen() -> None:
    payload = make_context()
    payload["context_version"] = "2"
    with pytest.raises(ValidationError):
        AgentContext.model_validate(payload)


def test_context_rejects_unknown_keys() -> None:
    payload = make_context()
    payload["surprise"] = 1
    with pytest.raises(ValidationError):
        AgentContext.model_validate(payload)


def test_prices_must_cover_the_whole_delivery_day() -> None:
    payload = make_context(steps=96, step_index=48)
    payload["market"]["prices_ron_mwh"] = [500.0] * 95
    with pytest.raises(ValidationError, match="whole delivery day"):
        AgentContext.model_validate(payload)


def test_negative_prices_are_allowed() -> None:
    payload = make_context()
    payload["market"]["prices_ron_mwh"][10] = -35.0
    context = AgentContext.model_validate(payload)
    assert context.market.prices_ron_mwh[10] == -35.0


def test_nan_prices_are_rejected() -> None:
    payload = make_context()
    payload["market"]["prices_ron_mwh"][0] = float("nan")
    with pytest.raises(ValidationError):
        AgentContext.model_validate(payload)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("pv", "forecast_mw"),
        ("pv", "realized_so_far_mw"),
        ("load", "forecast_mw"),
    ],
)
def test_series_lengths_must_match_the_step_index(section: str, field: str) -> None:
    payload = make_context()
    payload[section][field] = payload[section][field][:-1]
    with pytest.raises(ValidationError):
        AgentContext.model_validate(payload)


def test_execution_steps_is_min_16_remaining() -> None:
    payload = make_context(steps=96, step_index=48)
    payload["execution_steps"] = 15
    with pytest.raises(ValidationError, match="execution_steps"):
        AgentContext.model_validate(payload)


def test_dst_last_block_uses_twelve_steps() -> None:
    payload = make_context(steps=92, step_index=80)
    assert payload["steps_remaining"] == 12
    assert payload["execution_steps"] == 12
    context = AgentContext.model_validate(payload)
    assert context.execution_steps == 12

    payload["execution_steps"] = 16
    with pytest.raises(ValidationError, match="execution_steps"):
        AgentContext.model_validate(payload)


def test_previous_plan_lengths() -> None:
    context = AgentContext.model_validate(make_context(steps=96, step_index=0))
    assert context.previous_plan == []

    # A shorter previous block is legal (DST days can shorten the current window).
    payload = make_context()
    payload["previous_plan"] = [8] * 5
    assert AgentContext.model_validate(payload).previous_plan == [8] * 5

    payload["previous_plan"] = [8] * 17
    with pytest.raises(ValidationError, match="previous_plan"):
        AgentContext.model_validate(payload)


def test_previous_plan_may_exceed_the_current_dst_window() -> None:
    # At step 80 of a 92-interval day the current window is 12, but the plan made at
    # step 64 was 16 entries long.
    payload = make_context(steps=92, step_index=80)
    payload["previous_plan"] = [8] * 16
    context = AgentContext.model_validate(payload)
    assert context.execution_steps == 12
    assert len(context.previous_plan) == 16


def test_previous_plan_values_are_action_indices() -> None:
    payload = make_context()
    payload["previous_plan"][0] = ACTION_COUNT
    with pytest.raises(ValidationError, match="previous_plan"):
        AgentContext.model_validate(payload)


def test_battery_soc_must_be_within_bounds() -> None:
    payload = make_context()
    payload["battery"]["soc"] = 0.95
    with pytest.raises(ValidationError, match="soc must lie within"):
        AgentContext.model_validate(payload)


def test_battery_bounds_must_be_ordered() -> None:
    payload = make_context()
    payload["battery"]["soc_min"] = 0.9
    payload["battery"]["soc_max"] = 0.9
    with pytest.raises(ValidationError, match="soc_min"):
        AgentContext.model_validate(payload)


def test_time_utc_must_be_timezone_aware() -> None:
    payload = make_context()
    payload["time_utc"] = "2026-11-05T12:00:00"
    with pytest.raises(ValidationError, match="timezone-aware"):
        AgentContext.model_validate(payload)


def test_time_utc_is_normalized_to_utc() -> None:
    payload = make_context()
    payload["time_utc"] = "2026-11-05T14:00:00+02:00"
    context = AgentContext.model_validate(payload)
    assert context.time_utc == datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    assert context.time_utc.utcoffset() is not None


def test_limits_are_optional_but_positive_when_present() -> None:
    context = AgentContext.model_validate(make_context())
    assert context.limits.export_limit_mw is None

    payload = make_context()
    payload["limits"]["export_limit_mw"] = 0.0
    with pytest.raises(ValidationError):
        AgentContext.model_validate(payload)


# ---------------------------------------------------------------------------
# Schedule contract
# ---------------------------------------------------------------------------


def test_schedule_parses_llm_payload() -> None:
    payload = {
        "schedule": [
            {"interval": 0, "level": -0.5},
            {"interval": 1, "level": 0.0},
            {"interval": 2, "level": 1.0},
        ],
        "rationale": "charge early, sell the evening peak",
    }
    schedule = Schedule.model_validate(payload)
    assert schedule.action_indices() == [4, 8, 16]
    assert schedule.rationale.startswith("charge")


def test_schedule_from_action_indices_round_trips() -> None:
    schedule = Schedule.from_action_indices([0, 4, 8, 16], rationale="test")
    assert [entry.level for entry in schedule.schedule] == [-1.0, -0.5, 0.0, 1.0]
    assert schedule.action_indices() == [0, 4, 8, 16]


def test_schedule_level_tolerates_json_float_noise() -> None:
    schedule = Schedule.model_validate(
        {"schedule": [{"interval": 0, "level": -0.5000000001}]}
    )
    assert schedule.schedule[0].level == -0.5


def test_schedule_rejects_a_level_outside_the_17() -> None:
    with pytest.raises(ValidationError, match="signed action levels"):
        Schedule.model_validate({"schedule": [{"interval": 0, "level": 0.1}]})


def test_schedule_intervals_must_be_contiguous() -> None:
    with pytest.raises(ValidationError, match="interval"):
        Schedule.model_validate(
            {
                "schedule": [
                    {"interval": 0, "level": 0.0},
                    {"interval": 2, "level": 0.0},
                ]
            }
        )


def test_schedule_rejects_empty_and_oversized_payloads() -> None:
    with pytest.raises(ValidationError):
        Schedule.model_validate({"schedule": []})
    with pytest.raises(ValidationError):
        Schedule.from_action_indices([8] * 17)


def test_rationale_defaults_to_empty() -> None:
    schedule = Schedule.model_validate({"schedule": [{"interval": 0, "level": 0.0}]})
    assert schedule.rationale == ""


def test_validate_schedule_accepts_a_matching_length() -> None:
    context = AgentContext.model_validate(make_context())
    lookup = Schedule.from_action_indices([8] * 16)
    assert validate_schedule(lookup, context) == []


def test_validate_schedule_rejects_a_wrong_length() -> None:
    context = AgentContext.model_validate(make_context())
    lookup = Schedule.from_action_indices([8] * 15)
    errors = validate_schedule(lookup, context)
    assert errors == ["schedule length must equal execution_steps=16, got 15"]


def test_validate_schedule_returns_pydantic_errors() -> None:
    context = AgentContext.model_validate(make_context())
    errors = validate_schedule({"schedule": [{"interval": 0, "level": 0.1}]}, context)
    assert errors
    assert "signed action levels" in errors[0]


def test_validate_schedule_respects_a_dst_block_length() -> None:
    context = AgentContext.model_validate(make_context(steps=92, step_index=80))
    assert validate_schedule(Schedule.from_action_indices([8] * 12), context) == []
    errors = validate_schedule(Schedule.from_action_indices([8] * 16), context)
    assert errors and "execution_steps=12" in errors[0]


def test_parse_schedule_raises_with_all_errors() -> None:
    context = AgentContext.model_validate(make_context())
    with pytest.raises(ScheduleValidationError) as excinfo:
        parse_schedule({"schedule": [{"interval": 0, "level": 0.1}]}, context)
    assert excinfo.value.errors
    assert "signed action levels" in str(excinfo.value)


def test_schedule_soc_must_stay_within_bounds() -> None:
    battery = AgentContext.model_validate(make_context()).battery
    schedule = Schedule.from_action_indices([0] * 16)  # charge at full power
    errors = schedule.soc_errors(battery)
    assert errors
    assert "soc_max" in errors[0]
    assert len(errors) == MAX_SOC_ERRORS + 1
    assert errors[-1].startswith("... and")


def test_schedule_soc_check_can_be_disabled() -> None:
    context = AgentContext.model_validate(make_context())
    schedule = Schedule.from_action_indices([0] * 16)
    assert validate_schedule(schedule, context, check_soc=False) == []
    assert validate_schedule(schedule, context, check_soc=True)


def test_schedule_soc_is_feasible_at_an_exact_bound() -> None:
    battery = BatteryContext(
        capacity_mwh=10.0,
        p_max_mw=2.0,
        soc=0.8525,
        soc_min=0.10,
        soc_max=0.90,
        eta_c=0.95,
        eta_d=0.95,
        degradation_cost_ron_per_mwh=50.0,
    )
    schedule = Schedule.from_action_indices([0])  # one full charge: 8.525 + 0.475 = 9.0
    assert schedule.soc_errors(battery) == []


# ---------------------------------------------------------------------------
# Planner protocols
# ---------------------------------------------------------------------------


class _DummyPlanner:
    def plan(self, context: dict, execution_steps: int) -> list[int]:
        return [8] * execution_steps


class _DummyStepStrategy:
    def act(self, info: dict) -> int:
        return 8


def test_planner_protocol_is_runtime_checkable() -> None:
    assert isinstance(_DummyPlanner(), Planner)
    assert not isinstance(object(), Planner)


def test_step_strategy_protocol_is_runtime_checkable() -> None:
    assert isinstance(_DummyStepStrategy(), StepStrategy)
    assert not isinstance(object(), StepStrategy)
