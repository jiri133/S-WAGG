"""Tests for the LLM dispatch agent (mocked client; no API key or network)."""

from __future__ import annotations

import json

import pytest

from battery_rl.agents.llm import LLMAgent, LLMResponse, ToolCall
from battery_rl.agents.prompts import build_system_prompt, build_user_prompt
from battery_rl.agents.stub import StubLLMClient, StubSimulator
from battery_rl.agents.tools import (
    AgentTools,
    ScheduleValidationError,
    level_to_index,
    normalize_schedule,
)
from battery_rl.config import load_agent_config, load_env_config

ACTION_LEVELS = load_env_config().action_levels
ZERO = level_to_index(0.0, ACTION_LEVELS)
HALF = level_to_index(0.5, ACTION_LEVELS)
assert ZERO is not None and HALF is not None


def make_context(
    execution_steps: int = 16,
    steps_remaining: int = 48,
    step_index: int = 48,
) -> dict:
    return {
        "context_version": "1",
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
        },
        "market": {"currency": "RON", "prices_ron_mwh": [500.0] * 96},
        "pv": {
            "now_mw": 3.1,
            "forecast_mw": [1.0] * steps_remaining,
            "realized_so_far_mw": [0.0] * 48,
        },
        "load": {"now_mw": 5788.0, "forecast_mw": [5000.0] * steps_remaining},
        "limits": {"export_limit_mw": None, "import_limit_mw": None},
        "terminal_value": {"price_ron_mwh": 735.0, "mode": "episode_mean_price"},
        "previous_plan": [0] * execution_steps,
    }


class FakeClient:
    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def complete(
        self, messages: list[dict], *, tools: list[dict] | None = None
    ) -> LLMResponse:
        self.calls.append(list(messages))
        if not self.responses:
            raise AssertionError("no scripted response left")
        return self.responses.pop(0)


def json_response(
    levels: list[float],
    rationale: str = "test",
    confidence: float | None = 80.0,
) -> LLMResponse:
    payload = {
        "schedule": [
            {"interval": index, "level": level} for index, level in enumerate(levels)
        ],
        "rationale": rationale,
    }
    if confidence is not None:
        payload["confidence"] = confidence
    return LLMResponse(
        content=json.dumps(payload),
        prompt_tokens=100,
        completion_tokens=50,
        latency_s=0.1,
        model="fake",
    )


def tool_response(name: str, arguments: dict) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[ToolCall(id=f"call-{name}", name=name, arguments=arguments)],
        prompt_tokens=100,
        completion_tokens=50,
        latency_s=0.1,
        model="fake",
    )


def _agent(responses: list[LLMResponse], **kwargs) -> LLMAgent:
    return LLMAgent(
        load_agent_config(),
        client=FakeClient(responses),
        action_levels=ACTION_LEVELS,
        **kwargs,
    )


def test_json_schedule_is_parsed() -> None:
    agent = _agent([json_response([0.0] * 16)], simulator=StubSimulator())
    result = agent.plan_with_metadata(make_context(), 16)
    assert result.valid
    assert result.actions == [ZERO] * 16
    assert result.levels == [0.0] * 16
    assert result.confidence == 80.0
    assert result.usage["tokens_in"] == 100
    assert result.usage["tokens_out"] == 50
    assert result.usage["tool_calls"] == 0
    assert result.usage["valid"] is True


def test_plan_returns_action_indices() -> None:
    agent = _agent([json_response([0.5] * 16)], simulator=StubSimulator())
    assert agent.plan(make_context(), 16) == [HALF] * 16


def test_submit_tool_is_accepted() -> None:
    arguments = {
        "schedule": [
            {"interval": index, "level": 0.5} for index in range(16)
        ],
        "rationale": "submit",
        "confidence": 91,
    }
    agent = _agent([tool_response("submit_schedule", arguments)], simulator=StubSimulator())
    result = agent.plan_with_metadata(make_context(), 16)
    assert result.valid
    assert result.actions == [HALF] * 16
    assert result.confidence == 91.0
    assert result.usage["tool_calls"] == 1


def test_missing_confidence_is_none() -> None:
    agent = _agent(
        [json_response([0.0] * 16, confidence=None)],
        simulator=StubSimulator(),
    )
    result = agent.plan_with_metadata(make_context(), 16)
    assert result.valid
    assert result.confidence is None


def test_confidence_is_clamped_to_percent() -> None:
    high = _agent([json_response([0.0] * 16, confidence=140)], simulator=StubSimulator())
    low = _agent([json_response([0.0] * 16, confidence=-5)], simulator=StubSimulator())
    assert high.plan_with_metadata(make_context(), 16).confidence == 100.0
    assert low.plan_with_metadata(make_context(), 16).confidence == 0.0


def test_simulate_then_submit_uses_one_simulation() -> None:
    schedule = [{"interval": index, "level": 0.0} for index in range(16)]
    responses = [
        tool_response("simulate_schedule", {"schedule": schedule}),
        tool_response("submit_schedule", {"schedule": schedule, "rationale": "ok"}),
    ]
    agent = _agent(responses, simulator=StubSimulator())
    result = agent.plan_with_metadata(make_context(), 16)
    assert result.valid
    assert result.usage["tool_calls"] == 2


def test_simulate_unavailable_still_allows_submit() -> None:
    schedule = [{"interval": index, "level": 0.0} for index in range(16)]
    responses = [
        tool_response("simulate_schedule", {"schedule": schedule}),
        json_response([0.0] * 16),
    ]
    agent = _agent(responses, simulator=None)
    result = agent.plan_with_metadata(make_context(), 16)
    assert result.valid
    assert result.usage["tool_calls"] == 1


def test_invalid_schedule_retries_once() -> None:
    agent = _agent(
        [json_response([0.0] * 15), json_response([0.0] * 16)],
        simulator=StubSimulator(),
    )
    result = agent.plan_with_metadata(make_context(), 16)
    assert result.valid
    assert result.usage["retries"] == 1
    assert len(agent.client.calls) == 2


def test_invalid_level_retries_once() -> None:
    agent = _agent(
        [json_response([0.03] * 16), json_response([0.0] * 16)],
        simulator=StubSimulator(),
    )
    result = agent.plan_with_metadata(make_context(), 16)
    assert result.valid
    assert result.usage["retries"] == 1


def test_json_infeasible_schedule_falls_back() -> None:
    class InfeasibleSimulator:
        def simulate(self, context, actions, execution_steps):
            return {
                "net_cost_ron": 0.0,
                "soc_trajectory": [0.42] * execution_steps,
                "feasible": False,
                "violations_mwh": 0.1,
            }

    agent = _agent(
        [json_response([0.5] * 16), json_response([0.5] * 16)],
        simulator=InfeasibleSimulator(),
    )
    result = agent.plan_with_metadata(make_context(), 16)
    assert not result.valid
    assert result.fallback
    assert result.usage["retries"] == 1


def test_invalid_twice_falls_back_to_hold() -> None:
    agent = _agent(
        [json_response([0.0] * 15), json_response([0.0] * 15)],
        simulator=StubSimulator(),
    )
    result = agent.plan_with_metadata(make_context(), 16)
    assert not result.valid
    assert result.fallback
    assert result.actions == [ZERO] * 16
    assert result.usage["fallback"] is True


def test_stub_client_adapts_to_execution_window() -> None:
    agent = LLMAgent(
        load_agent_config(),
        client=StubLLMClient(),
        simulator=StubSimulator(),
        action_levels=ACTION_LEVELS,
    )
    result = agent.plan_with_metadata(make_context(execution_steps=4), 4)
    assert result.valid
    assert len(result.actions) == 4


def test_tools_validate_length_and_levels() -> None:
    with pytest.raises(ScheduleValidationError, match="16"):
        normalize_schedule([0.0] * 15, 16, ACTION_LEVELS)
    with pytest.raises(ScheduleValidationError, match="allowed"):
        normalize_schedule([0.03] * 16, 16, ACTION_LEVELS)
    levels = normalize_schedule(
        [{"interval": 0, "level": 0.0}] + [0.0] * 15, 16, ACTION_LEVELS
    )
    assert levels == [0.0] * 16


def test_tools_enforce_max_simulator_calls() -> None:
    tools = AgentTools(
        context=make_context(),
        execution_steps=16,
        action_levels=ACTION_LEVELS,
        simulator=StubSimulator(),
        max_simulator_calls=1,
    )
    first = tools.simulate_schedule([0.0] * 16)
    second = tools.simulate_schedule([0.0] * 16)
    assert first["available"] is True
    assert second["available"] is False


def test_infeasible_submit_is_rejected() -> None:
    class InfeasibleSimulator:
        def simulate(self, context, actions, execution_steps):
            return {
                "net_cost_ron": 0.0,
                "soc_trajectory": [0.42] * execution_steps,
                "feasible": False,
                "violations_mwh": 0.1,
            }

    tools = AgentTools(
        context=make_context(),
        execution_steps=16,
        action_levels=ACTION_LEVELS,
        simulator=InfeasibleSimulator(),
    )
    result = tools.submit_schedule([0.0] * 16)
    assert result["accepted"] is False
    assert "infeasible" in result["error"]


def test_agent_telemetry_accumulates() -> None:
    agent = _agent([json_response([0.0] * 16)], simulator=StubSimulator())
    agent.plan_with_metadata(make_context(), 16)
    telemetry = agent.telemetry
    assert telemetry.decisions == 1
    assert telemetry.feasible == 1
    assert telemetry.invalid == 0
    assert telemetry.tool_calls == 0
    assert telemetry.input_tokens == 100
    assert telemetry.output_tokens == 50
    assert telemetry.latency_s == pytest.approx(0.1)
    assert telemetry.cost_ron > 0.0


def test_cost_uses_cache_split_and_peak_multiplier() -> None:
    config = load_agent_config()
    agent = LLMAgent(config, client=StubLLMClient(), action_levels=ACTION_LEVELS)
    response = LLMResponse(
        content=None,
        prompt_tokens=2_000_000,
        completion_tokens=1_000_000,
        cache_hit_tokens=500_000,
        cache_miss_tokens=1_500_000,
    )
    pricing = config.pricing
    expected_usd = (
        0.5 * pricing.input_cache_hit_usd_per_million
        + 1.5 * pricing.input_cache_miss_usd_per_million
        + 1.0 * pricing.output_usd_per_million
    )
    peak_cost, peak_usd = agent._response_cost(response, peak=True)
    offpeak_cost, offpeak_usd = agent._response_cost(response, peak=False)
    assert peak_usd == pytest.approx(expected_usd)
    assert peak_cost == pytest.approx(expected_usd * pricing.usd_to_ron)
    assert offpeak_usd == pytest.approx(expected_usd * pricing.offpeak_multiplier)
    assert offpeak_cost == pytest.approx(peak_cost * pricing.offpeak_multiplier)


def test_cost_defaults_to_cache_miss_when_split_is_missing() -> None:
    agent = _agent([json_response([0.0] * 16)])
    result = agent.plan_with_metadata(make_context(), 16)
    pricing = load_agent_config().pricing
    # 100 input tokens as cache miss, 50 output tokens; the context is 12:00 UTC (off-peak).
    expected_usd = 0.5 * (
        100 / 1_000_000 * pricing.input_cache_miss_usd_per_million
        + 50 / 1_000_000 * pricing.output_usd_per_million
    )
    assert result.usage["cost_usd"] == pytest.approx(expected_usd)
    assert result.usage["cost_ron"] == pytest.approx(expected_usd * pricing.usd_to_ron)
    assert agent.telemetry.cost_ron == pytest.approx(result.usage["cost_ron"])


def test_one_day_six_decisions_with_stubs() -> None:
    agent = LLMAgent(
        load_agent_config(),
        client=StubLLMClient(),
        simulator=StubSimulator(),
        action_levels=ACTION_LEVELS,
    )
    decisions = 0
    for step_index in (0, 16, 32, 48, 64, 80):
        remaining = 96 - step_index
        execution = min(16, remaining)
        context = make_context(
            execution_steps=execution,
            steps_remaining=remaining,
            step_index=step_index,
        )
        result = agent.plan_with_metadata(context, execution)
        assert result.valid
        assert len(result.actions) == execution
        assert all(0 <= action < len(ACTION_LEVELS) for action in result.actions)
        assert result.usage["tokens_in"] > 0
        decisions += 1
    assert decisions == 6


def test_prompt_contains_merchant_contract() -> None:
    system = build_system_prompt(load_agent_config(), ACTION_LEVELS)
    assert "merchant" in system.lower()
    assert "no local load" in system.lower()
    assert "simulate_schedule" in system
    assert "-0.5" in system
    assert "opportunity cost" in system
    assert "end of the delivery day" in " ".join(system.split())
    assert "Do not call those tools" in system

    user = build_user_prompt(make_context(), 16)
    assert "site_demand_mw: 0.0" in user
    assert "idx,time_utc,price_ron_mwh,pv_forecast_mw,load_forecast_mw" in user
    assert "execution_steps: 16" in user
    assert "Return exactly" in user
    assert "round_trip_efficiency:" in user
    assert "terminal_value_ron_per_mwh:" in user
    assert "degradation_cost_ron_per_mwh=" in user
    assert "cheapest_remaining_intervals:" in user
    assert "most_expensive_remaining_intervals:" in user
