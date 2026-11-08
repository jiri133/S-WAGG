"""Integration tests: LLM agent + lane B runner, metrics and simulator adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from battery_rl.agents.llm import LLMAgent
from battery_rl.agents.simulator import ContextSimulator
from battery_rl.agents.stub import StubLLMClient
from battery_rl.config import load_agent_config, load_env_config, load_farm_config
from battery_rl.data.dataset import DayData, load_days
from battery_rl.env.context import build_context_dict
from battery_rl.env.env import BatteryEnv
from battery_rl.eval.runner import run_day

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"
HOLD = 8


def load_fixture(name: str = "tiny_day") -> DayData:
    days = load_days(FIXTURES / f"{name}.csv")
    return next(iter(days.values()))


def test_llm_agent_runs_through_runner_and_reports_telemetry() -> None:
    farm = load_farm_config()
    env_config = load_env_config()
    env = BatteryEnv.from_farm(load_fixture(), farm, env_config)
    agent = LLMAgent(
        load_agent_config(),
        client=StubLLMClient(),
        simulator=ContextSimulator(dt_h=env_config.step_minutes / 60.0),
        action_levels=env_config.action_levels,
    )

    result = run_day(env, agent, farm=farm, mode="block")

    assert len(result.records) == 96
    assert result.metrics["llm_tokens"] == 6 * (10 + 10)
    assert result.metrics["llm_feasible_rate"] == pytest.approx(1.0)
    assert result.metrics["llm_invalid_rate"] == pytest.approx(0.0)
    assert result.metrics["llm_tool_calls"] == 0
    assert agent.telemetry.decisions == 6
    assert agent.telemetry.feasible == 6
    assert agent.telemetry.invalid == 0


def test_context_simulator_replays_hold_schedule() -> None:
    farm = load_farm_config()
    env_config = load_env_config()
    env = BatteryEnv.from_farm(load_fixture(), farm, env_config)
    env.reset()
    context = build_context_dict(env, farm)

    simulator = ContextSimulator(dt_h=env_config.step_minutes / 60.0)
    result = simulator.simulate(context, [HOLD] * 16, 16)

    assert result["feasible"] is True
    assert result["violations_mwh"] == pytest.approx(0.0)
    assert len(result["soc_trajectory"]) == 16
    assert all(
        context["battery"]["soc_min"]
        <= soc
        <= context["battery"]["soc_max"]
        for soc in result["soc_trajectory"]
    )
    assert result["net_cost_ron"] == pytest.approx(
        result["import_cost_ron"] - result["export_revenue_ron"]
    )
    assert result["score_ron"] == pytest.approx(
        -result["net_cost_ron"]
        - result["degradation_ron"]
        - result["violation_penalty_ron"]
    )


def test_context_simulator_rejects_short_schedule() -> None:
    farm = load_farm_config()
    env_config = load_env_config()
    env = BatteryEnv.from_farm(load_fixture(), farm, env_config)
    env.reset()
    context = build_context_dict(env, farm)
    simulator = ContextSimulator(dt_h=env_config.step_minutes / 60.0)

    with pytest.raises(ValueError, match="expected 16"):
        simulator.simulate(context, [HOLD] * 15, 16)
