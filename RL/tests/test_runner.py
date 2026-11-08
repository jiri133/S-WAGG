"""Runner contract tests: modes, repeats, DST, regimes, CSV and oracle context."""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from battery_rl.config import load_env_config, load_farm_config
from battery_rl.data.dataset import DayData, load_days
from battery_rl.env.env import BatteryEnv
from battery_rl.eval.runner import (
    CSV_FIELDS,
    REGIMES,
    StrategySpec,
    build_oracle_context,
    classify_day,
    compute_regime_thresholds,
    run_day,
    run_split,
    state_info,
    usable_days,
    write_csv,
)
from battery_rl.strategies.idle import Idle
from battery_rl.strategies.price_threshold import PriceThreshold

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"


def load_fixture(name: str) -> DayData:
    days = load_days(FIXTURES / f"{name}.csv")
    return next(iter(days.values()))


def make_env(day: DayData | None = None) -> BatteryEnv:
    day = day if day is not None else load_fixture("tiny_day")
    return BatteryEnv.from_farm(day, load_farm_config(), load_env_config())


def idle_spec() -> StrategySpec:
    return StrategySpec("idle", lambda day, env: Idle(), ("step", "block"))


def test_state_info_is_the_pre_step_state() -> None:
    env = make_env()
    env.reset()
    info = state_info(env)
    day = env.day
    assert day is not None
    assert info["step_index"] == 0
    assert info["soc"] == pytest.approx(0.5)
    assert info["pv_mw"] == pytest.approx(float(day.pv_mw[0]))
    assert info["price_ron_mwh"] == pytest.approx(float(day.price_ron_mwh[0]))
    assert str(info["timestamp_utc"]).endswith("Z")


def test_idle_step_and_block_are_identical() -> None:
    env = make_env()
    farm = load_farm_config()
    step = run_day(env, Idle(), farm=farm, mode="step")
    block = run_day(env, Idle(), farm=farm, mode="block")

    assert len(step.records) == 96
    assert len(block.records) == 96
    assert step.metrics["throughput_mwh"] == pytest.approx(0.0)
    assert block.metrics["throughput_mwh"] == pytest.approx(0.0)
    assert step.metrics["net_cost_ron"] == pytest.approx(
        block.metrics["net_cost_ron"]
    )
    assert step.score_ron == pytest.approx(block.score_ron)


def test_mode_capability_errors() -> None:
    env = make_env()
    farm = load_farm_config()

    class OnlyAct:
        def act(self, info: dict) -> int:
            return 8

    class OnlyPlan:
        def plan(self, context: dict, execution_steps: int) -> list[int]:
            return [8] * execution_steps

    class ShortPlan(OnlyPlan):
        def plan(self, context: dict, execution_steps: int) -> list[int]:
            return [8] * (execution_steps - 1)

    with pytest.raises(TypeError, match="Planner"):
        run_day(env, OnlyAct(), farm=farm, mode="block")
    with pytest.raises(TypeError, match="StepStrategy"):
        run_day(env, OnlyPlan(), farm=farm, mode="step")
    with pytest.raises(ValueError, match="mode"):
        run_day(env, Idle(), farm=farm, mode="nope")
    with pytest.raises(ValueError, match="expected"):
        run_day(env, ShortPlan(), farm=farm, mode="block")


def test_run_split_counts_repeats_and_csv(tmp_path: Path) -> None:
    days = [load_fixture("tiny_day"), load_fixture("tiny_day_spring")]
    specs = [
        idle_spec(),
        StrategySpec(
            "price_threshold",
            lambda day, env: PriceThreshold(env.spec, prices=day.price_ron_mwh),
            ("block",),
        ),
    ]
    results = run_split(
        days,
        specs,
        farm=load_farm_config(),
        env_config=load_env_config(),
        repeats=2,
    )
    # 2 days x (idle step + idle block + price block) x 2 repeats.
    assert len(results) == 12
    assert all(result.records == [] for result in results)

    path = write_csv(results, tmp_path / "results.csv")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == CSV_FIELDS
        rows = list(reader)
    assert len(rows) == 12
    assert all(row["regimes"] is not None for row in rows)

    idle_step = [
        result
        for result in results
        if result.strategy == "idle" and result.mode == "step"
        and result.day == days[0].day
    ]
    assert len(idle_step) == 2
    assert idle_step[0].metrics["net_cost_ron"] == pytest.approx(
        idle_step[1].metrics["net_cost_ron"]
    )


def test_keep_records_and_dst_length() -> None:
    spring = load_fixture("tiny_day_spring")
    results = run_split(
        [spring],
        [idle_spec()],
        farm=load_farm_config(),
        env_config=load_env_config(),
        repeats=1,
        keep_records=True,
    )
    assert len(results) == 2
    for result in results:
        assert result.day == spring.day
        assert len(result.records) == 92


def test_run_split_is_deterministic() -> None:
    days = [load_fixture("tiny_day")]
    specs = [
        idle_spec(),
        StrategySpec(
            "price_threshold",
            lambda day, env: PriceThreshold(env.spec, prices=day.price_ron_mwh),
            ("block",),
        ),
    ]
    first = run_split(
        days,
        specs,
        farm=load_farm_config(),
        env_config=load_env_config(),
        repeats=1,
    )
    second = run_split(
        days,
        specs,
        farm=load_farm_config(),
        env_config=load_env_config(),
        repeats=1,
    )
    assert len(first) == len(second) == 3
    for left, right in zip(first, second, strict=True):
        assert left.strategy == right.strategy
        assert left.mode == right.mode
        assert left.metrics == right.metrics
        assert left.score_ron == pytest.approx(right.score_ron)


def test_regime_classification() -> None:
    tiny = load_fixture("tiny_day")
    spring = load_fixture("tiny_day_spring")
    fall = load_fixture("tiny_day_fall")
    thresholds = compute_regime_thresholds([tiny, spring, fall])

    assert "weekend" in classify_day(spring, thresholds)  # Sunday
    assert "weekend" in classify_day(fall, thresholds)  # Sunday
    assert "weekend" not in classify_day(tiny, thresholds)  # Thursday
    for day in (tiny, spring, fall):
        assert set(classify_day(day, thresholds)) <= set(REGIMES)


def test_usable_days_filters_incomplete_days() -> None:
    day = load_fixture("tiny_day")
    incomplete = replace(day, is_complete=np.zeros(day.intervals, dtype=bool))
    assert usable_days([day, incomplete]) == [day]

    results = run_split(
        [incomplete, day],
        [idle_spec()],
        farm=load_farm_config(),
        env_config=load_env_config(),
        repeats=1,
    )
    assert {result.day for result in results} == {day.day}


def test_oracle_context_replaces_pv_with_actuals() -> None:
    env = make_env()
    env.reset()
    for _ in range(10):
        env.step(8)
    day = env.day
    assert day is not None
    context = build_oracle_context(env, load_farm_config())
    assert context["pv"]["now_mw"] == pytest.approx(float(day.pv_mw[10]))
    assert context["pv"]["forecast_mw"] == pytest.approx(
        [float(value) for value in day.pv_mw[10:]]
    )
    assert context["pv"]["realized_so_far_mw"] == pytest.approx(
        [float(value) for value in day.pv_mw[:10]]
    )
