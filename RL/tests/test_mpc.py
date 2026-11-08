"""MPC and perfect-foresight LP tests: solution shape, feasibility and ordering."""

from __future__ import annotations

from pathlib import Path

import pytest

from battery_rl.config import load_env_config, load_farm_config
from battery_rl.data.dataset import DayData, load_days
from battery_rl.env.battery import BatterySpec
from battery_rl.env.context import build_context_dict
from battery_rl.env.env import BatteryEnv
from battery_rl.eval.runner import build_oracle_context, run_day
from battery_rl.strategies.idle import Idle
from battery_rl.strategies.lp import solve_battery_lp
from battery_rl.strategies.mpc import MPC
from battery_rl.strategies.oracle_lp import OracleLP
from battery_rl.strategies.rule_based import RuleBased

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"
SPEC = BatterySpec(capacity_mwh=10.0, p_max_mw=2.0)


def load_fixture(name: str) -> DayData:
    days = load_days(FIXTURES / f"{name}.csv")
    return next(iter(days.values()))


def make_env(day: DayData | None = None) -> BatteryEnv:
    day = day if day is not None else load_fixture("tiny_day")
    return BatteryEnv.from_farm(day, load_farm_config(), load_env_config())


def reset_env(day: DayData | None = None) -> BatteryEnv:
    env = make_env(day)
    env.reset()
    return env


# ---------------------------------------------------------------------------
# LP core
# ---------------------------------------------------------------------------


def test_lp_charges_low_and_discharges_high() -> None:
    # Start at soc_min so the only way to sell at the high price is to charge first.
    solution = solve_battery_lp(
        [10.0, 100.0],
        [0.0, 0.0],
        SPEC,
        start_soc=0.1,
        degradation_cost_ron_per_mwh=0.0,
        terminal_price_ron_mwh=None,
    )
    assert solution.charge_mw[0] == pytest.approx(2.0)
    assert solution.discharge_mw[1] == pytest.approx(2.0 * 0.95**2)
    assert solution.energy_mwh[0] == pytest.approx(1.0)
    assert solution.energy_mwh[-1] == pytest.approx(1.0, abs=1e-6)
    # Revenue: 100 * 1.805 * 0.25 = 45.125, minus 10 * 2 * 0.25 = 5.
    assert solution.objective_ron == pytest.approx(-40.125, abs=1e-6)


def test_lp_terminal_value_fills_the_battery() -> None:
    solution = solve_battery_lp(
        [100.0] * 10,
        [0.0] * 10,
        SPEC,
        start_soc=0.5,
        degradation_cost_ron_per_mwh=0.0,
        terminal_price_ron_mwh=10_000.0,
    )
    assert solution.energy_mwh[-1] == pytest.approx(9.0)


def test_lp_energy_balance_and_bounds() -> None:
    solution = solve_battery_lp(
        [50.0, 400.0, 50.0, 400.0, 50.0],
        [0.0] * 5,
        SPEC,
        start_soc=0.5,
        degradation_cost_ron_per_mwh=25.0,
        terminal_price_ron_mwh=300.0,
    )
    for index in range(5):
        expected = (
            solution.energy_mwh[index]
            + SPEC.eta_c * 0.25 * solution.charge_mw[index]
            - 0.25 / SPEC.eta_d * solution.discharge_mw[index]
        )
        assert solution.energy_mwh[index + 1] == pytest.approx(expected)
    assert all(1.0 - 1e-9 <= value <= 9.0 + 1e-9 for value in solution.energy_mwh)


def test_lp_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="prices"):
        solve_battery_lp(
            [],
            None,
            SPEC,
            start_soc=0.5,
            degradation_cost_ron_per_mwh=0.0,
            terminal_price_ron_mwh=None,
        )
    with pytest.raises(ValueError, match="pv_mw"):
        solve_battery_lp(
            [1.0, 2.0],
            [1.0],
            SPEC,
            start_soc=0.5,
            degradation_cost_ron_per_mwh=0.0,
            terminal_price_ron_mwh=None,
        )
    with pytest.raises(ValueError, match="start_soc"):
        solve_battery_lp(
            [1.0],
            None,
            SPEC,
            start_soc=0.95,
            degradation_cost_ron_per_mwh=0.0,
            terminal_price_ron_mwh=None,
        )
    with pytest.raises(ValueError, match="finite"):
        solve_battery_lp(
            [float("nan")],
            None,
            SPEC,
            start_soc=0.5,
            degradation_cost_ron_per_mwh=0.0,
            terminal_price_ron_mwh=None,
        )


# ---------------------------------------------------------------------------
# MPC and oracle behaviour
# ---------------------------------------------------------------------------


def test_mpc_beats_rule_based_and_oracle_is_the_upper_bound() -> None:
    env = make_env()
    farm = load_farm_config()
    idle = run_day(env, Idle(), farm=farm, mode="block")
    rule = run_day(env, RuleBased(env.spec), farm=farm, mode="block")
    mpc = run_day(env, MPC(), farm=farm, mode="block")
    oracle = run_day(
        env,
        OracleLP(),
        farm=farm,
        mode="block",
        context_builder=build_oracle_context,
    )

    assert mpc.score_ron > rule.score_ron
    assert mpc.score_ron > idle.score_ron
    assert oracle.score_ron >= mpc.score_ron - 1e-6
    assert all(record["feasible"] for record in mpc.records)
    assert all(record["feasible"] for record in oracle.records)
    assert mpc.metrics["throughput_mwh"] > 0.0


def test_mpc_plan_length_on_a_short_dst_block() -> None:
    env = reset_env(load_fixture("tiny_day_spring"))
    for _ in range(80):
        env.step(8)
    context = build_context_dict(env, load_farm_config(), previous_plan=[8] * 16)
    execution_steps = context["execution_steps"]
    assert execution_steps == 12

    plan = MPC().plan(context, execution_steps)
    assert len(plan) == 12

    env.reset()
    for _ in range(80):
        env.step(8)
    results = [env.step(action) for action in plan]
    assert all(result.info["feasible"] for result in results)


def test_mpc_rejects_a_mismatched_execution_window() -> None:
    env = reset_env()
    context = build_context_dict(env, load_farm_config())
    with pytest.raises(ValueError, match="execution_steps"):
        MPC().plan(context, 15)


def test_oracle_context_uses_actual_pv() -> None:
    env = reset_env()
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
