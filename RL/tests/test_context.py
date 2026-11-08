"""Versioned context contract tests: lengths, causality and farm/battery values."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from battery_rl.agents.schemas import AgentContext
from battery_rl.config import (
    EnvConfig,
    FarmConfig,
    ObjectiveConfig,
    load_env_config,
    load_farm_config,
)
from battery_rl.data.dataset import DayData, load_days
from battery_rl.env.battery import BatterySpec
from battery_rl.env.context import build_context, build_context_dict
from battery_rl.env.env import BatteryEnv

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"


def load_fixture(name: str) -> DayData:
    days = load_days(FIXTURES / f"{name}.csv")
    return next(iter(days.values()))


def make_env(
    day: DayData | None = None, config: EnvConfig | None = None
) -> BatteryEnv:
    day = day if day is not None else load_fixture("tiny_day")
    farm = load_farm_config()
    return BatteryEnv(
        day,
        BatterySpec.from_farm_config(farm),
        config if config is not None else load_env_config(),
    )


def test_context_at_day_start() -> None:
    day = load_fixture("tiny_day")
    env = make_env(day)
    env.reset()
    farm = load_farm_config()
    context = build_context(env, farm)

    assert isinstance(context, AgentContext)
    assert context.context_version == "1"
    assert context.delivery_day == date(2026, 1, 15)
    assert context.time_utc == datetime(2026, 1, 14, 22, 0, tzinfo=UTC)
    assert context.step_index == 0
    assert context.steps_remaining == 96
    assert context.execution_steps == 16

    assert len(context.market.prices_ron_mwh) == 96
    assert context.market.prices_ron_mwh == pytest.approx(list(day.price_ron_mwh))
    assert context.market.currency == "RON"

    assert len(context.pv.forecast_mw) == 96
    assert context.pv.realized_so_far_mw == []
    assert context.pv.now_mw == pytest.approx(float(day.pv_forecast_mw[0]))

    assert len(context.load.forecast_mw) == 96
    assert context.load.now_mw == pytest.approx(float(day.load_forecast_mw[0]))

    assert context.previous_plan == []
    assert context.battery.capacity_mwh == pytest.approx(10.0)
    assert context.battery.p_max_mw == pytest.approx(2.0)
    assert context.battery.soc == pytest.approx(0.5)
    assert context.battery.soc_min == pytest.approx(0.10)
    assert context.battery.soc_max == pytest.approx(0.90)
    assert context.battery.eta_c == pytest.approx(0.95)
    assert context.battery.eta_d == pytest.approx(0.95)
    assert context.battery.degradation_cost_ron_per_mwh == pytest.approx(50.0)

    assert context.farm.name == farm.name
    assert context.farm.lat == pytest.approx(46.7744)
    assert context.farm.lon == pytest.approx(25.9308)
    assert context.farm.kwp == pytest.approx(6000.0)
    assert context.farm.asset_scale == pytest.approx(1.0)

    assert context.limits.export_limit_mw is None
    assert context.limits.import_limit_mw is None
    assert context.terminal_value.mode == "episode_mean_price"
    assert context.terminal_value.price_ron_mwh == pytest.approx(
        float(np.mean(day.price_ron_mwh))
    )


def test_context_midday_window_lengths() -> None:
    day = load_fixture("tiny_day")
    env = make_env(day)
    env.reset()
    for _ in range(16):
        env.step(8)

    context = build_context(env, load_farm_config(), previous_plan=[8] * 16)
    assert context.step_index == 16
    assert context.steps_remaining == 80
    assert context.execution_steps == 16
    assert len(context.market.prices_ron_mwh) == 96
    assert len(context.pv.forecast_mw) == 80
    assert len(context.pv.realized_so_far_mw) == 16
    assert len(context.load.forecast_mw) == 80
    assert context.previous_plan == [8] * 16
    assert context.battery.soc == pytest.approx(env.soc)

    assert np.allclose(context.pv.realized_so_far_mw, day.pv_mw[:16])
    assert np.allclose(context.pv.forecast_mw, day.pv_forecast_mw[16:])
    assert np.allclose(context.load.forecast_mw, day.load_forecast_mw[16:])


def test_context_causality_uses_only_past_actuals() -> None:
    day = load_fixture("tiny_day")
    env = make_env(day)
    env.reset()
    for _ in range(32):
        env.step(8)

    context = build_context(env, load_farm_config())
    assert len(context.pv.realized_so_far_mw) == context.step_index == 32
    assert np.allclose(context.pv.realized_so_far_mw, day.pv_mw[:32])
    # "now" and the forecast come from the forecast column, never the actual column.
    assert context.pv.now_mw == pytest.approx(float(day.pv_forecast_mw[32]))
    assert np.allclose(context.pv.forecast_mw, day.pv_forecast_mw[32:])
    assert context.load.now_mw == pytest.approx(float(day.load_forecast_mw[32]))
    assert len(context.pv.forecast_mw) == context.steps_remaining


def test_context_on_spring_dst_last_block() -> None:
    day = load_fixture("tiny_day_spring")
    env = make_env(day)
    env.reset()
    for _ in range(80):
        env.step(8)

    # The plan at step 64 was 16 entries; the current window is only 12.
    context = build_context(env, load_farm_config(), previous_plan=[8] * 16)
    assert context.step_index == 80
    assert context.steps_remaining == 12
    assert context.execution_steps == 12
    assert len(context.market.prices_ron_mwh) == 92
    assert len(context.pv.forecast_mw) == 12
    assert len(context.pv.realized_so_far_mw) == 80
    assert len(context.load.forecast_mw) == 12
    assert len(context.previous_plan) == 16


def test_context_on_fall_dst_day() -> None:
    day = load_fixture("tiny_day_fall")
    env = make_env(day)
    env.reset()
    for _ in range(80):
        env.step(8)

    context = build_context(env, load_farm_config(), previous_plan=[8] * 16)
    assert context.steps_remaining == 20
    assert context.execution_steps == 16
    assert len(context.market.prices_ron_mwh) == 100
    assert len(context.pv.forecast_mw) == 20
    assert len(context.pv.realized_so_far_mw) == 80


def test_context_requires_reset_and_a_running_episode() -> None:
    env = make_env()
    farm = load_farm_config()
    with pytest.raises(RuntimeError, match="reset"):
        build_context(env, farm)

    env.reset()
    for _ in range(96):
        env.step(8)
    with pytest.raises(RuntimeError, match="complete"):
        build_context(env, farm)


def test_context_validates_the_previous_plan() -> None:
    env = make_env()
    env.reset()
    for _ in range(16):
        env.step(8)
    farm = load_farm_config()

    with pytest.raises(ValidationError):
        build_context(env, farm, previous_plan=[8] * 17)
    with pytest.raises(ValidationError):
        build_context(env, farm, previous_plan=[99])


def test_context_dict_is_json_safe_and_round_trips() -> None:
    env = make_env()
    env.reset()
    farm = load_farm_config()

    payload = build_context_dict(env, farm)
    assert isinstance(payload, dict)
    assert payload["context_version"] == "1"
    assert payload["delivery_day"] == "2026-01-15"
    assert str(payload["time_utc"]).endswith("Z")
    json.dumps(payload)
    assert AgentContext.model_validate(payload) == build_context(env, farm)


def test_context_terminal_value_modes() -> None:
    fixed = EnvConfig(
        objective=ObjectiveConfig(
            terminal_value_mode="fixed",
            terminal_reference_price_ron_per_mwh=123.0,
        )
    )
    fixed_env = make_env(config=fixed)
    fixed_env.reset()
    fixed_context = build_context(fixed_env, load_farm_config())
    assert fixed_context.terminal_value.mode == "fixed"
    assert fixed_context.terminal_value.price_ron_mwh == pytest.approx(123.0)

    none = EnvConfig(objective=ObjectiveConfig(terminal_value_mode="none"))
    none_env = make_env(config=none)
    none_env.reset()
    none_context = build_context(none_env, load_farm_config())
    assert none_context.terminal_value.mode == "none"
    assert none_context.terminal_value.price_ron_mwh == pytest.approx(0.0)


def test_context_takes_limits_from_the_farm_config() -> None:
    farm = load_farm_config()
    limited = FarmConfig.model_validate(
        {
            **farm.model_dump(),
            "grid": {"export_limit_mw": 1.5, "import_limit_mw": 2.5},
        }
    )
    env = BatteryEnv.from_farm(load_fixture("tiny_day"), limited, load_env_config())
    env.reset()
    context = build_context(env, limited)
    assert context.limits.export_limit_mw == pytest.approx(1.5)
    assert context.limits.import_limit_mw == pytest.approx(2.5)
