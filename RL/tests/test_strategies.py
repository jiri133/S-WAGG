"""Baseline strategy tests: idle, merchant rule-based, and price threshold."""

from __future__ import annotations

from pathlib import Path

import pytest

from battery_rl.agents.base import Planner, StepStrategy
from battery_rl.config import load_env_config, load_farm_config
from battery_rl.data.dataset import DayData, load_days
from battery_rl.env.battery import BatterySpec
from battery_rl.env.context import build_context_dict
from battery_rl.env.env import BatteryEnv
from battery_rl.strategies.common import (
    FULL_CHARGE_ACTION,
    FULL_DISCHARGE_ACTION,
    HOLD_ACTION,
)
from battery_rl.strategies.idle import Idle
from battery_rl.strategies.price_threshold import PriceThreshold
from battery_rl.strategies.rule_based import RuleBased

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"
SPEC = BatterySpec(capacity_mwh=10.0, p_max_mw=2.0)


def load_fixture(name: str) -> DayData:
    days = load_days(FIXTURES / f"{name}.csv")
    return next(iter(days.values()))


def make_env(day: DayData | None = None) -> BatteryEnv:
    day = day if day is not None else load_fixture("tiny_day")
    farm = load_farm_config()
    return BatteryEnv.from_farm(day, farm, load_env_config())


def reset_env(day: DayData | None = None) -> BatteryEnv:
    env = make_env(day)
    env.reset()
    return env


# ---------------------------------------------------------------------------
# Idle
# ---------------------------------------------------------------------------


def test_idle_holds_everywhere() -> None:
    idle = Idle()
    assert idle.act({}) == HOLD_ACTION
    env = reset_env()
    context = build_context_dict(env, load_farm_config())
    assert idle.plan(context, 16) == [HOLD_ACTION] * 16
    with pytest.raises(ValueError, match="execution_steps"):
        idle.plan(context, 0)


def test_idle_day_has_zero_throughput() -> None:
    env = reset_env()
    for _ in range(96):
        env.step(HOLD_ACTION)
    assert env.total_degradation_ron == pytest.approx(0.0)
    assert all(record["feasible"] for record in env.records)
    assert all(record["p_charge_mw"] == 0 for record in env.records)
    assert all(record["p_discharge_mw"] == 0 for record in env.records)


# ---------------------------------------------------------------------------
# RuleBased
# ---------------------------------------------------------------------------


def test_rule_based_charges_at_the_pv_level() -> None:
    rule = RuleBased(SPEC)
    assert rule.act({"soc": 0.5, "pv_mw": 2.0}) == FULL_CHARGE_ACTION
    assert rule.act({"soc": 0.5, "pv_mw": 1.0}) == 4
    assert rule.act({"soc": 0.5, "pv_mw": 0.5}) == 6
    # Below the smallest action step (0.25 MW): hold instead of importing.
    assert rule.act({"soc": 0.5, "pv_mw": 0.1}) == HOLD_ACTION


def test_rule_based_discharges_without_pv() -> None:
    rule = RuleBased(SPEC)
    assert rule.act({"soc": 0.5, "pv_mw": 0.0}) == FULL_DISCHARGE_ACTION
    # Deadband holds at the lower bound (soc_min + 0.02).
    assert rule.act({"soc": 0.12, "pv_mw": 0.0}) == HOLD_ACTION
    # Just above the deadband: 0.836 MW feasible -> level 0.375 (index 11).
    assert rule.act({"soc": 0.122, "pv_mw": 0.0}) == 11
    assert rule.act({"soc": 0.105, "pv_mw": 0.0}) == HOLD_ACTION
    assert rule.act({"soc": 0.895, "pv_mw": 2.0}) == HOLD_ACTION


def test_rule_based_day_never_imports() -> None:
    env = reset_env()
    day = env.day
    assert day is not None
    rule = RuleBased(env.spec)
    for index in range(day.intervals):
        info = {
            "soc": env.soc,
            "pv_mw": float(day.pv_mw[index]),
            "price_ron_mwh": float(day.price_ron_mwh[index]),
        }
        result = env.step(rule.act(info))
        assert result.info["import_mw"] == pytest.approx(0.0)
        assert result.info["feasible"] is True
    assert env.total_degradation_ron > 0.0


def test_rule_based_plan_is_feasible() -> None:
    env = reset_env()
    context = build_context_dict(env, load_farm_config())
    plan = RuleBased(env.spec).plan(context, 16)
    assert len(plan) == 16
    env.reset()
    results = [env.step(action) for action in plan]
    assert all(result.info["feasible"] for result in results)


# ---------------------------------------------------------------------------
# PriceThreshold
# ---------------------------------------------------------------------------


def test_price_threshold_actions() -> None:
    strategy = PriceThreshold(
        SPEC, low_price_ron_mwh=300.0, high_price_ron_mwh=700.0
    )
    assert strategy.act({"soc": 0.5, "price_ron_mwh": 200.0}) == FULL_CHARGE_ACTION
    assert strategy.act({"soc": 0.5, "price_ron_mwh": 800.0}) == FULL_DISCHARGE_ACTION
    assert strategy.act({"soc": 0.5, "price_ron_mwh": 500.0}) == HOLD_ACTION
    assert strategy.act({"soc": 0.105, "price_ron_mwh": 800.0}) == HOLD_ACTION
    assert strategy.act({"soc": 0.895, "price_ron_mwh": 200.0}) == HOLD_ACTION


def test_price_threshold_quantiles() -> None:
    prices = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0]
    strategy = PriceThreshold(SPEC, prices)
    assert strategy.low_price_ron_mwh == pytest.approx(370.0)
    assert strategy.high_price_ron_mwh == pytest.approx(730.0)
    with pytest.raises(ValueError, match="quantiles"):
        PriceThreshold(SPEC, prices, low_quantile=0.8, high_quantile=0.5)
    with pytest.raises(ValueError, match="provide prices"):
        PriceThreshold(SPEC)


def test_price_threshold_day_outperforms_idle() -> None:
    idle_env = reset_env()
    for _ in range(96):
        idle_env.step(HOLD_ACTION)

    env = reset_env()
    day = env.day
    assert day is not None
    strategy = PriceThreshold(env.spec, prices=day.price_ron_mwh)
    for index in range(day.intervals):
        info = {
            "soc": env.soc,
            "price_ron_mwh": float(day.price_ron_mwh[index]),
        }
        result = env.step(strategy.act(info))
        assert result.info["feasible"] is True
    assert env.total_degradation_ron > 0.0
    assert env.total_cost_ron < idle_env.total_cost_ron


def test_price_threshold_plan_is_feasible() -> None:
    env = reset_env()
    day = env.day
    assert day is not None
    context = build_context_dict(env, load_farm_config())
    plan = PriceThreshold(env.spec, prices=day.price_ron_mwh).plan(context, 16)
    assert len(plan) == 16
    env.reset()
    results = [env.step(action) for action in plan]
    assert all(result.info["feasible"] for result in results)


# ---------------------------------------------------------------------------
# DST and protocols
# ---------------------------------------------------------------------------


def test_plans_use_the_short_dst_last_block() -> None:
    env = reset_env(load_fixture("tiny_day_spring"))
    for _ in range(80):
        env.step(HOLD_ACTION)
    context = build_context_dict(env, load_farm_config(), previous_plan=[8] * 16)
    assert context["execution_steps"] == 12

    day = env.day
    assert day is not None
    strategies = (
        Idle(),
        RuleBased(env.spec),
        PriceThreshold(env.spec, prices=day.price_ron_mwh),
    )
    for strategy in strategies:
        assert len(strategy.plan(context, 12)) == 12


def test_strategies_satisfy_both_protocols() -> None:
    strategies = (
        Idle(),
        RuleBased(SPEC),
        PriceThreshold(SPEC, low_price_ron_mwh=300.0, high_price_ron_mwh=700.0),
    )
    for strategy in strategies:
        assert isinstance(strategy, StepStrategy)
        assert isinstance(strategy, Planner)
