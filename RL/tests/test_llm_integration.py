"""Integration tests: LLM agent + lane B runner, metrics and simulator adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from battery_rl.agents.llm import LLMAgent
from battery_rl.agents.prompts import PROMPT_VERSION
from battery_rl.agents.simulator import ContextSimulator
from battery_rl.agents.stub import StubLLMClient
from battery_rl.config import load_agent_config, load_env_config, load_farm_config
from battery_rl.data.dataset import DayData, load_days
from battery_rl.env.context import build_context_dict
from battery_rl.env.env import BatteryEnv
from battery_rl.eval.runner import StrategySpec, run_day, run_split

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
    assert len(agent.transcripts) == 6
    first = agent.transcripts[0]
    assert first["prompt_version"] == PROMPT_VERSION
    assert first["result"]["valid"] is True
    assert first["result"]["confidence"] == 80.0
    assert first["messages"][0]["role"] == "system"
    assert first["messages"][1]["role"] == "user"
    assert first["usage"]["tokens_in"] == 10


def test_runner_writes_one_jsonl_transcript_per_run(tmp_path: Path) -> None:
    farm = load_farm_config()
    env_config = load_env_config()

    def factory(_day: DayData, env: BatteryEnv) -> LLMAgent:
        return LLMAgent(
            load_agent_config(),
            client=StubLLMClient(),
            simulator=ContextSimulator(dt_h=env_config.step_minutes / 60.0),
            action_levels=env_config.action_levels,
        )

    spec = StrategySpec("llm", factory, ("block",))
    run_split(
        [load_fixture()],
        [spec],
        farm=farm,
        env_config=env_config,
        repeats=1,
        transcript_dir=tmp_path,
    )

    files = sorted(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    assert files[0].name.endswith("_llm_block_r0.jsonl")
    decisions = [
        json.loads(line)
        for line in files[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(decisions) == 6
    assert {decision["prompt_version"] for decision in decisions} == {PROMPT_VERSION}
    assert all(decision["result"]["valid"] for decision in decisions)
    assert all(decision["usage"]["tokens_in"] == 10 for decision in decisions)


def _llm_spec(factory=None) -> StrategySpec:
    env_config = load_env_config()
    if factory is None:

        def factory(_day: DayData, env: BatteryEnv) -> LLMAgent:
            return LLMAgent(
                load_agent_config(),
                client=StubLLMClient(),
                simulator=ContextSimulator(dt_h=env_config.step_minutes / 60.0),
                action_levels=env_config.action_levels,
            )

    return StrategySpec("llm", factory, ("block",))


def test_resume_replays_transcripts_without_calling_the_client(
    tmp_path: Path,
) -> None:
    farm = load_farm_config()
    env_config = load_env_config()
    day = load_fixture()
    first = run_split(
        [day],
        [_llm_spec()],
        farm=farm,
        env_config=env_config,
        repeats=1,
        transcript_dir=tmp_path,
    )
    assert len(first) == 1

    def exploding_factory(_day: DayData, env: BatteryEnv) -> LLMAgent:
        raise AssertionError("factory must not be called when resuming")

    resumed = run_split(
        [day],
        [_llm_spec(exploding_factory)],
        farm=farm,
        env_config=env_config,
        repeats=1,
        transcript_dir=tmp_path,
        resume=True,
        prompt_version=PROMPT_VERSION,
    )

    assert len(resumed) == 1
    assert resumed[0].score_ron == pytest.approx(first[0].score_ron)
    assert resumed[0].metrics["llm_tokens"] == first[0].metrics["llm_tokens"]
    assert (
        resumed[0].metrics["llm_feasible_rate"]
        == first[0].metrics["llm_feasible_rate"]
    )
    assert resumed[0].metrics["net_cost_ron"] == pytest.approx(
        first[0].metrics["net_cost_ron"]
    )


def test_resume_rejects_a_different_prompt_version(tmp_path: Path) -> None:
    farm = load_farm_config()
    env_config = load_env_config()
    day = load_fixture()
    run_split(
        [day],
        [_llm_spec()],
        farm=farm,
        env_config=env_config,
        repeats=1,
        transcript_dir=tmp_path,
    )

    with pytest.raises(ValueError, match="prompt version"):
        run_split(
            [day],
            [_llm_spec()],
            farm=farm,
            env_config=env_config,
            repeats=1,
            transcript_dir=tmp_path,
            resume=True,
            prompt_version="v999",
        )


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
