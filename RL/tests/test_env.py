"""Environment contract tests: reset/step, info, DST lengths, conservation and scoring."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest

from battery_rl.agents.schemas import ACTION_LEVELS
from battery_rl.config import (
    EnvConfig,
    FarmConfig,
    ObjectiveConfig,
    load_env_config,
    load_farm_config,
)
from battery_rl.data.dataset import DayData, load_days
from battery_rl.env.battery import BatterySpec
from battery_rl.env.env import INFO_KEYS, BatteryEnv, EnvState
from battery_rl.seeding import make_rng

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"
DT_H = 0.25
P_MAX = 2.0
CAPACITY = 10.0


def load_fixture(name: str) -> DayData:
    days = load_days(FIXTURES / f"{name}.csv")
    return next(iter(days.values()))


def make_env(day: DayData | None = None, config: EnvConfig | None = None) -> BatteryEnv:
    day = day if day is not None else load_fixture("tiny_day")
    farm = load_farm_config()
    return BatteryEnv(
        day,
        BatterySpec.from_farm_config(farm),
        config if config is not None else load_env_config(),
    )


# ---------------------------------------------------------------------------
# Reset and info contract
# ---------------------------------------------------------------------------


def test_reset_returns_initial_state() -> None:
    env = make_env()
    state = env.reset()
    assert isinstance(state, EnvState)
    assert state.day == date(2026, 1, 15)
    assert state.step_index == 0
    assert state.steps_remaining == 96
    assert state.soc == pytest.approx(0.5)
    assert state.energy_mwh == pytest.approx(5.0)
    assert state.timestamp_utc == datetime(2026, 1, 14, 22, 0, tzinfo=UTC)


def test_step_hold_matches_the_info_contract() -> None:
    env = make_env()
    env.reset()
    day = env.day
    assert day is not None
    result = env.step(8)
    info = result.info

    assert set(info) == INFO_KEYS
    assert info["step_index"] == 0
    assert info["timestamp_utc"] == "2026-01-14T22:00:00Z"
    assert info["pv_mw"] == pytest.approx(float(day.pv_mw[0]))
    assert info["load_mw"] == pytest.approx(float(day.load_mw[0]))
    assert info["price_ron_mwh"] == pytest.approx(float(day.price_ron_mwh[0]))
    assert info["soc"] == pytest.approx(0.5)
    assert info["soc_next"] == pytest.approx(0.5)
    assert info["p_charge_mw"] == pytest.approx(0.0)
    assert info["p_discharge_mw"] == pytest.approx(0.0)
    assert info["requested_level"] == 0.0
    assert info["executed_level"] == 0.0
    assert info["feasible"] is True
    assert info["violation_mwh"] == pytest.approx(0.0)
    assert info["degradation_ron"] == pytest.approx(0.0)

    expected_cost = (
        float(day.price_ron_mwh[0])
        * max(float(day.load_mw[0]) - float(day.pv_mw[0]), 0.0)
        * DT_H
    )
    assert info["cost_ron"] == pytest.approx(expected_cost)
    assert result.terminated is False
    assert result.truncated is False
    assert result.state.step_index == 1
    assert result.state.soc == pytest.approx(info["soc_next"])
    assert env.records == [info]


def test_charge_level_sign_and_efficiency() -> None:
    env = make_env()
    env.reset()
    info = env.step(0).info
    assert info["requested_level"] == -1.0
    assert info["executed_level"] == pytest.approx(-1.0)
    assert info["p_charge_mw"] == pytest.approx(P_MAX)
    assert info["p_discharge_mw"] == pytest.approx(0.0)
    assert info["soc"] == pytest.approx(0.5)
    assert info["soc_next"] == pytest.approx(0.5475)
    assert info["degradation_ron"] == pytest.approx(50.0 * P_MAX * DT_H * 0.95)
    assert info["feasible"] is True


def test_discharge_level_sign_and_efficiency() -> None:
    env = make_env()
    env.reset()
    info = env.step(16).info
    assert info["requested_level"] == 1.0
    assert info["executed_level"] == pytest.approx(1.0)
    assert info["p_discharge_mw"] == pytest.approx(P_MAX)
    assert info["p_charge_mw"] == pytest.approx(0.0)
    assert info["soc_next"] == pytest.approx(0.5 - P_MAX * DT_H / 0.95 / CAPACITY)
    assert info["degradation_ron"] == pytest.approx(50.0 * P_MAX * DT_H / 0.95)


def test_all_seventeen_levels_map_to_the_contract() -> None:
    env = make_env()
    for index, level in enumerate(ACTION_LEVELS):
        env.reset()
        info = env.step(index).info
        assert info["requested_level"] == pytest.approx(level)
        assert info["executed_level"] == pytest.approx(level)


def test_battery_clipping_is_reported_in_info() -> None:
    env = make_env()
    env.reset(soc=0.88)
    info = env.step(0).info
    assert info["requested_level"] == -1.0
    assert info["executed_level"] == pytest.approx(-0.42105263157894735)
    assert info["p_charge_mw"] == pytest.approx(0.8421052631578947)
    assert info["soc_next"] == pytest.approx(0.9)
    assert info["feasible"] is False
    assert info["violation_mwh"] == pytest.approx((P_MAX - 0.8421052631578947) * DT_H)


def test_timestamps_advance_by_one_interval() -> None:
    env = make_env()
    env.reset()
    assert env.step(8).info["timestamp_utc"] == "2026-01-14T22:00:00Z"
    assert env.step(8).info["timestamp_utc"] == "2026-01-14T22:15:00Z"


# ---------------------------------------------------------------------------
# Episode control
# ---------------------------------------------------------------------------


def test_action_validation() -> None:
    env = make_env()
    env.reset()
    for invalid in (-1, 17):
        with pytest.raises(ValueError, match="action index"):
            env.step(invalid)
    for invalid in (8.0, True, "8"):
        with pytest.raises(TypeError, match="action must be an int"):
            env.step(invalid)  # type: ignore[arg-type]
    # NumPy integer indices are accepted for callers that do not cast.
    assert env.step(np.int64(8)).info["requested_level"] == 0.0


def test_step_before_reset_and_after_done() -> None:
    env = make_env()
    with pytest.raises(RuntimeError, match="reset"):
        env.step(8)
    env.reset()
    for _ in range(96):
        env.step(8)
    assert env.done
    with pytest.raises(RuntimeError, match="finished"):
        env.step(8)


@pytest.mark.parametrize(
    ("name", "intervals", "expected_start"),
    [
        ("tiny_day", 96, datetime(2026, 1, 14, 22, 0, tzinfo=UTC)),
        ("tiny_day_spring", 92, datetime(2026, 3, 28, 22, 0, tzinfo=UTC)),
        ("tiny_day_fall", 100, datetime(2026, 10, 24, 21, 0, tzinfo=UTC)),
    ],
)
def test_variable_day_lengths(
    name: str, intervals: int, expected_start: datetime
) -> None:
    env = make_env(load_fixture(name))
    state = env.reset()
    assert state.steps_remaining == intervals
    assert state.timestamp_utc == expected_start

    last = None
    for _ in range(intervals):
        last = env.step(8)
    assert last is not None
    assert last.truncated is True
    assert env.done
    assert env.steps_remaining == 0
    assert len(env.records) == intervals


def test_day_selection() -> None:
    day = load_fixture("tiny_day")
    env = make_env(day)
    with pytest.raises(KeyError, match="not loaded"):
        env.reset(date(2030, 1, 1))

    other = load_fixture("tiny_day_spring")
    multi = BatteryEnv(
        [day, other],
        BatterySpec.from_farm_config(load_farm_config()),
        load_env_config(),
    )
    with pytest.raises(ValueError, match="day is required"):
        multi.reset()
    state = multi.reset(other.day)
    assert state.day == other.day
    assert state.steps_remaining == 92


def test_reset_soc_override() -> None:
    env = make_env()
    assert env.reset(soc=0.3).soc == pytest.approx(0.3)
    with pytest.raises(ValueError, match="initial soc"):
        env.reset(soc=0.95)


# ---------------------------------------------------------------------------
# Day validation
# ---------------------------------------------------------------------------


def test_incomplete_day_is_rejected() -> None:
    day = load_fixture("tiny_day")
    incomplete = replace(
        day, is_complete=np.zeros(day.intervals, dtype=bool)
    )
    with pytest.raises(ValueError, match="incomplete"):
        make_env().reset(incomplete)


def test_malformed_day_is_rejected() -> None:
    day = load_fixture("tiny_day")
    env = make_env()
    short = replace(day, price_ron_mwh=day.price_ron_mwh[:-1])
    with pytest.raises(ValueError, match="price_ron_mwh"):
        env.reset(short)
    nan_pv = replace(day, pv_mw=np.full(day.intervals, np.nan))
    with pytest.raises(ValueError, match="non-finite"):
        env.reset(nan_pv)
    negative_pv = replace(day, pv_mw=np.zeros(day.intervals))
    negative_pv = replace(negative_pv, pv_mw=negative_pv.pv_mw - 1.0)
    with pytest.raises(ValueError, match="negative"):
        env.reset(negative_pv)


# ---------------------------------------------------------------------------
# Economics and conservation
# ---------------------------------------------------------------------------


def test_energy_conservation_and_economics_over_a_day() -> None:
    env = make_env()
    env.reset()
    rng = make_rng(11)
    for _ in range(96):
        info = env.step(int(rng.integers(0, 17))).info
        assert (
            info["pv_mw"]
            + info["import_mw"]
            + info["p_discharge_mw"]
            == pytest.approx(
                info["load_mw"]
                + info["p_charge_mw"]
                + info["export_mw"]
                + info["curtailed_mw"]
            )
        )
        assert 0.1 - 1e-9 <= info["soc_next"] <= 0.9 + 1e-9
        assert info["cost_ron"] == pytest.approx(
            info["price_ron_mwh"] * (info["import_mw"] - info["export_mw"]) * DT_H
        )
        throughput = (
            info["p_charge_mw"] * DT_H * 0.95
            + info["p_discharge_mw"] * DT_H / 0.95
        )
        assert info["degradation_ron"] == pytest.approx(50.0 * throughput)
        assert info["executed_level"] == pytest.approx(
            (info["p_discharge_mw"] - info["p_charge_mw"]) / P_MAX
        )
        if info["feasible"]:
            assert info["violation_mwh"] == pytest.approx(0.0)
        else:
            assert info["violation_mwh"] > 0.0


def test_zero_penalties_score_equals_negative_cash_flow() -> None:
    config = EnvConfig(
        objective=ObjectiveConfig(
            degradation_cost_ron_per_mwh=0.0,
            violation_penalty_ron_per_mwh=0.0,
            terminal_value_mode="none",
        )
    )
    env = make_env(config=config)
    env.reset()
    rng = make_rng(3)
    for _ in range(96):
        env.step(int(rng.integers(0, 17)))
    assert env.total_degradation_ron == pytest.approx(0.0)
    assert env.total_violation_penalty_ron == pytest.approx(0.0)
    assert env.episode_score_ron == pytest.approx(-env.total_cost_ron)


def test_terminal_value_modes() -> None:
    day = load_fixture("tiny_day")
    farm = load_farm_config()

    mean_env = BatteryEnv(day, BatterySpec.from_farm_config(farm), load_env_config())
    mean_env.reset(soc=0.5)
    mean_price = float(np.mean(day.price_ron_mwh))
    assert mean_env.terminal_price_ron_mwh == pytest.approx(mean_price)
    assert mean_env.episode_score_ron == pytest.approx(mean_price * 5.0 * 0.95)

    fixed_config = EnvConfig(
        objective=ObjectiveConfig(
            degradation_cost_ron_per_mwh=0.0,
            violation_penalty_ron_per_mwh=0.0,
            terminal_value_mode="fixed",
            terminal_reference_price_ron_per_mwh=123.0,
        )
    )
    fixed_env = make_env(config=fixed_config)
    fixed_env.reset(soc=0.5)
    assert fixed_env.terminal_price_ron_mwh == 123.0
    assert fixed_env.episode_score_ron == pytest.approx(123.0 * 5.0 * 0.95)

    none_config = EnvConfig(
        objective=ObjectiveConfig(
            degradation_cost_ron_per_mwh=0.0,
            violation_penalty_ron_per_mwh=0.0,
            terminal_value_mode="none",
        )
    )
    none_env = make_env(config=none_config)
    none_env.reset(soc=0.5)
    assert none_env.terminal_price_ron_mwh == 0.0
    assert none_env.episode_score_ron == pytest.approx(0.0)

    missing_config = EnvConfig(
        objective=ObjectiveConfig(
            terminal_value_mode="fixed",
            terminal_reference_price_ron_per_mwh=None,
        )
    )
    with pytest.raises(ValueError, match="terminal_reference_price"):
        make_env(config=missing_config).reset()


def test_records_and_totals() -> None:
    env = make_env()
    env.reset()
    first = env.step(8)
    second = env.step(0)
    assert env.records == [first.info, second.info]
    assert env.total_cost_ron == pytest.approx(
        first.info["cost_ron"] + second.info["cost_ron"]
    )
    assert env.total_degradation_ron == pytest.approx(
        first.info["degradation_ron"] + second.info["degradation_ron"]
    )


def test_from_farm_uses_scaled_spec_and_grid_limits() -> None:
    farm = load_farm_config()
    limited = FarmConfig.model_validate(
        {
            **farm.model_dump(),
            "grid": {"export_limit_mw": 1.5, "import_limit_mw": 2.5},
        }
    )
    env = BatteryEnv.from_farm(load_fixture("tiny_day"), limited, load_env_config())
    env.reset()
    assert env.spec.capacity_mwh == pytest.approx(10.0)
    assert env.spec.p_max_mw == pytest.approx(2.0)
    assert env.export_limit_mw == pytest.approx(1.5)
    assert env.import_limit_mw == pytest.approx(2.5)
