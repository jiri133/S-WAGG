"""LLM dispatch agent (Phase 7, lane A3).

The agent implements the frozen ``Planner.plan(context, execution_steps)``
contract.  It uses a DeepSeek model through an OpenAI-compatible endpoint and
exposes the four tools from the plan.  The simulator is injected, so lane B's
env/runner can be plugged in without changing this module; tests use the stubs
in ``agents/stub.py``.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from ..config import AgentConfig, load_env_config
from ..credentials import agent_api_key, agent_base_url
from .prompts import PROMPT_VERSION, build_system_prompt, build_user_prompt
from .tools import (
    AgentTools,
    ScheduleValidationError,
    level_to_index,
    normalize_schedule,
    to_jsonable,
)

LOGGER = logging.getLogger("battery_rl.agents.llm")


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    latency_s: float = 0.0
    model: str = ""


class LLMClient(Protocol):
    def complete(
        self, messages: list[dict], *, tools: list[dict] | None = None
    ) -> LLMResponse: ...


@dataclass
class PlanResult:
    actions: list[int]
    levels: list[float]
    usage: dict[str, Any]
    valid: bool
    fallback: bool
    rationale: str | None = None
    error: str | None = None


class DeepSeekClient:
    """OpenAI-compatible client for DeepSeek and similar endpoints."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        max_output_tokens: int = 4096,
        timeout: float = 60.0,
        max_retries: int = 0,
    ):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise RuntimeError(
                "The 'openai' package is required for the DeepSeek client. "
                "Install the RL package or run: pip install 'openai>=1.0'"
            ) from exc
        self.model = model
        self.max_output_tokens = max_output_tokens
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    @classmethod
    def from_config(
        cls,
        config: AgentConfig,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> DeepSeekClient:
        return cls(
            api_key=agent_api_key(config),
            base_url=agent_base_url(config),
            model=config.model_id,
            max_output_tokens=config.max_output_tokens,
            timeout=config.request_timeout_s if timeout is None else timeout,
            max_retries=(
                config.client_max_retries if max_retries is None else max_retries
            ),
        )

    def complete(
        self, messages: list[dict], *, tools: list[dict] | None = None
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": self.max_output_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        started = time.perf_counter()
        response = self._client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - started

        choice = response.choices[0]
        message = choice.message
        tool_calls: list[ToolCall] = []
        for index, call in enumerate(message.tool_calls or []):
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                ToolCall(
                    id=call.id or f"call_{index}",
                    name=call.function.name,
                    arguments=arguments,
                )
            )
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        cache_hit_tokens = int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0)
        cache_miss_value = getattr(usage, "prompt_cache_miss_tokens", None)
        cache_miss_tokens = (
            int(cache_miss_value)
            if cache_miss_value is not None
            else max(prompt_tokens - cache_hit_tokens, 0)
        )
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cache_hit_tokens=cache_hit_tokens,
            cache_miss_tokens=cache_miss_tokens,
            latency_s=latency,
            model=getattr(response, "model", self.model),
        )


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_peak_hour(value: object) -> bool:
    """DeepSeek peak pricing: 01:00-04:00 and 06:00-10:00 UTC, Monday-Friday.

    Chinese public holidays are ignored; treating them as peak is conservative.
    """
    parsed = _parse_utc(value)
    if parsed is None:
        return True
    if parsed.weekday() >= 5:
        return False
    hour = parsed.hour
    return 1 <= hour < 4 or 6 <= hour < 10


def _strip_code_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = value[3:]
        if value.lower().startswith("json"):
            value = value[4:]
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    return value.strip()


class LLMAgent:
    """Planner implementation backed by a chat model with tool calls."""

    MAX_TOOL_ROUNDS = 6

    def __init__(
        self,
        config: AgentConfig,
        *,
        client: LLMClient | None = None,
        simulator=None,
        action_levels: list[float] | None = None,
        fallback: Callable[[dict, int], list[int]] | None = None,
    ):
        self.config = config
        self.client = client if client is not None else DeepSeekClient.from_config(config)
        self.simulator = simulator
        if action_levels is None:
            action_levels = load_env_config().action_levels
        self.action_levels = list(action_levels)
        self.fallback = fallback
        self.last_result: PlanResult | None = None
        self.transcripts: list[dict[str, Any]] = []
        self._decisions = 0
        self._feasible = 0
        self._invalid = 0
        self._tool_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._latency_s = 0.0
        self._cost_ron = 0.0
        if config.prompt_version != PROMPT_VERSION:
            LOGGER.warning(
                "agent.yaml prompt_version=%s but prompts module is %s",
                config.prompt_version,
                PROMPT_VERSION,
            )
        if config.fallback == "rule_based" and fallback is None:
            LOGGER.warning(
                "fallback=rule_based but no rule-based callable was injected; using hold"
            )

    def plan(self, context: dict, execution_steps: int) -> list[int]:
        """Planner protocol: return one action index per execution interval."""

        return self.plan_with_metadata(context, execution_steps).actions

    @property
    def telemetry(self):
        """Per-day usage summary consumed by ``eval.runner`` and ``eval.metrics``."""

        from ..eval.metrics import LLMTelemetry

        return LLMTelemetry(
            decisions=self._decisions,
            feasible=self._feasible,
            invalid=self._invalid,
            tool_calls=self._tool_calls,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            latency_s=self._latency_s,
            cost_ron=self._cost_ron,
        )

    def _record_usage(self, usage: dict[str, Any], *, feasible: bool) -> None:
        self._tool_calls += int(usage["tool_calls"])
        self._input_tokens += int(usage["tokens_in"])
        self._output_tokens += int(usage["tokens_out"])
        self._latency_s += float(usage["latency_s"])
        self._cost_ron += float(usage["cost_ron"])
        if feasible:
            self._feasible += 1
        else:
            self._invalid += 1

    def plan_with_metadata(
        self, context: dict, execution_steps: int
    ) -> PlanResult:
        started = time.perf_counter()
        self._decisions += 1
        system_prompt = build_system_prompt(self.config, self.action_levels)
        user_prompt = build_user_prompt(context, execution_steps)
        usage: dict[str, Any] = {
            "model": self.config.model_id,
            "prompt_version": self.config.prompt_version,
            "tokens_in": 0,
            "tokens_out": 0,
            "cache_hit_tokens": 0,
            "cache_miss_tokens": 0,
            "cost_ron": 0.0,
            "cost_usd": 0.0,
            "latency_s": 0.0,
            "wall_s": 0.0,
            "tool_calls": 0,
            "retries": 0,
            "fallback": False,
            "valid": False,
        }
        transcript: dict[str, Any] = {
            "model_id": self.config.model_id,
            "prompt_version": self.config.prompt_version,
            "delivery_day": context.get("delivery_day"),
            "time_utc": context.get("time_utc"),
            "step_index": context.get("step_index"),
            "execution_steps": execution_steps,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "attempts": [],
            "rounds": [],
            "messages": [],
            "usage": usage,
            "result": None,
        }
        error: str | None = None
        peak = _is_peak_hour(context.get("time_utc"))

        for attempt in range(self.config.max_retries + 1):
            messages: list[dict] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            if error:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The previous answer was invalid: {error}. "
                            "Return a corrected schedule with one level per "
                            f"{execution_steps} execution intervals."
                        ),
                    }
                )
            tools = AgentTools(
                context=context,
                execution_steps=execution_steps,
                action_levels=self.action_levels,
                simulator=self.simulator,
                max_simulator_calls=self.config.max_simulator_calls,
            )
            try:
                result = self._run_loop(
                    messages,
                    tools,
                    usage,
                    transcript["rounds"],
                    attempt=attempt,
                    peak=peak,
                )
            except Exception as exc:  # network/SDK errors are retried then fallback
                LOGGER.warning(
                    "LLM attempt %d failed: %s: %s",
                    attempt,
                    type(exc).__name__,
                    exc,
                )
                result = PlanResult(
                    actions=[],
                    levels=[],
                    usage=usage,
                    valid=False,
                    fallback=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            transcript["attempts"].append(
                {
                    "attempt": attempt,
                    "valid": result.valid,
                    "error": result.error,
                }
            )
            transcript["messages"] = [dict(message) for message in messages]
            if result.valid:
                usage["valid"] = True
                usage["wall_s"] = time.perf_counter() - started
                self._record_usage(usage, feasible=True)
                self.last_result = result
                self._record_transcript(transcript, result)
                return result
            error = result.error or "invalid schedule"
            if attempt < self.config.max_retries:
                usage["retries"] += 1
                time.sleep(min(2.0 * (attempt + 1), 5.0))

        actions = self._fallback(context, execution_steps)
        levels = [float(self.action_levels[action]) for action in actions]
        usage["fallback"] = True
        usage["wall_s"] = time.perf_counter() - started
        self._record_usage(usage, feasible=False)
        self.last_result = PlanResult(
            actions=actions,
            levels=levels,
            usage=usage,
            valid=False,
            fallback=True,
            rationale="fallback",
            error=error,
        )
        self._record_transcript(transcript, self.last_result)
        return self.last_result

    def _record_transcript(
        self, transcript: dict[str, Any], result: PlanResult
    ) -> None:
        """Store one decision's prompts, conversation, tool calls and outcome."""
        transcript["usage"] = dict(result.usage)
        transcript["result"] = {
            "valid": result.valid,
            "fallback": result.fallback,
            "actions": list(result.actions),
            "levels": list(result.levels),
            "rationale": result.rationale,
            "error": result.error,
        }
        self.transcripts.append(transcript)

    def _response_cost(
        self, response: LLMResponse, *, peak: bool
    ) -> tuple[float, float]:
        """Return ``(cost_ron, cost_usd)`` for one API response."""
        pricing = self.config.pricing
        multiplier = 1.0 if peak else pricing.offpeak_multiplier
        cache_hit = response.cache_hit_tokens
        cache_miss = response.cache_miss_tokens
        # Clients that do not report cache splits are charged the cache-miss rate.
        if cache_hit + cache_miss == 0 and response.prompt_tokens > 0:
            cache_miss = response.prompt_tokens
        cost_usd = multiplier * (
            cache_hit / 1_000_000.0 * pricing.input_cache_hit_usd_per_million
            + cache_miss / 1_000_000.0 * pricing.input_cache_miss_usd_per_million
            + response.completion_tokens
            / 1_000_000.0
            * pricing.output_usd_per_million
        )
        return cost_usd * pricing.usd_to_ron, cost_usd

    def _run_loop(
        self,
        messages: list[dict],
        tools: AgentTools,
        usage: dict[str, Any],
        rounds: list[dict[str, Any]],
        *,
        attempt: int = 0,
        peak: bool = True,
    ) -> PlanResult:
        for round_index in range(self.MAX_TOOL_ROUNDS):
            response = self.client.complete(
                messages, tools=tools.tool_definitions()
            )
            usage["tokens_in"] += response.prompt_tokens
            usage["tokens_out"] += response.completion_tokens
            usage["cache_hit_tokens"] += response.cache_hit_tokens
            usage["cache_miss_tokens"] += response.cache_miss_tokens
            usage["latency_s"] += response.latency_s
            cost_ron, cost_usd = self._response_cost(response, peak=peak)
            usage["cost_ron"] += cost_ron
            usage["cost_usd"] += cost_usd
            rounds.append(
                {
                    "attempt": attempt,
                    "round": round_index,
                    "model": response.model,
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "cache_hit_tokens": response.cache_hit_tokens,
                    "cache_miss_tokens": response.cache_miss_tokens,
                    "cost_ron": cost_ron,
                    "cost_usd": cost_usd,
                    "latency_s": response.latency_s,
                    "content": response.content,
                    "tool_calls": [
                        {"name": call.name, "arguments": call.arguments}
                        for call in response.tool_calls
                    ],
                }
            )

            if response.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or None,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(call.arguments),
                                },
                            }
                            for call in response.tool_calls
                        ],
                    }
                )
                for call in response.tool_calls:
                    usage["tool_calls"] += 1
                    tool_result = tools.dispatch(call.name, call.arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(to_jsonable(tool_result)),
                        }
                    )
                    if call.name == "submit_schedule" and tools.submitted is not None:
                        return self._result_from_levels(
                            tools.submitted, tools.rationale, usage
                        )
                continue

            if response.content:
                try:
                    payload = json.loads(_strip_code_fence(response.content))
                except (json.JSONDecodeError, TypeError) as exc:
                    return PlanResult(
                        actions=[],
                        levels=[],
                        usage=usage,
                        valid=False,
                        fallback=False,
                        error=f"invalid JSON: {exc}",
                    )
                if not isinstance(payload, dict) or "schedule" not in payload:
                    return PlanResult(
                        actions=[],
                        levels=[],
                        usage=usage,
                        valid=False,
                        fallback=False,
                        error="response JSON has no 'schedule'",
                    )
                try:
                    levels = normalize_schedule(
                        payload["schedule"],
                        tools.execution_steps,
                        self.action_levels,
                    )
                except ScheduleValidationError as exc:
                    return PlanResult(
                        actions=[],
                        levels=[],
                        usage=usage,
                        valid=False,
                        fallback=False,
                        error=str(exc),
                    )
                # Run the same acceptance path as the tool so SoC feasibility is
                # checked for direct JSON schedules too.
                accepted = tools.submit_schedule(
                    payload["schedule"], payload.get("rationale")
                )
                if not accepted.get("accepted"):
                    return PlanResult(
                        actions=[],
                        levels=[],
                        usage=usage,
                        valid=False,
                        fallback=False,
                        error=str(accepted.get("error", "schedule rejected")),
                    )
                return self._result_from_levels(
                    tools.submitted or levels,
                    tools.rationale or payload.get("rationale"),
                    usage,
                )

            return PlanResult(
                actions=[],
                levels=[],
                usage=usage,
                valid=False,
                fallback=False,
                error="empty response",
            )

        return PlanResult(
            actions=[],
            levels=[],
            usage=usage,
            valid=False,
            fallback=False,
            error="tool loop exhausted",
        )

    def _result_from_levels(
        self,
        levels: list[float],
        rationale: str | None,
        usage: dict[str, Any],
    ) -> PlanResult:
        actions: list[int] = []
        for index, level in enumerate(levels):
            action = level_to_index(level, self.action_levels)
            if action is None:
                raise ScheduleValidationError(
                    f"entry {index}: level {level} is not an allowed level"
                )
            actions.append(action)
        return PlanResult(
            actions=actions,
            levels=list(levels),
            usage=usage,
            valid=True,
            fallback=False,
            rationale=rationale,
        )

    def _fallback(self, context: dict, execution_steps: int) -> list[int]:
        if self.fallback is not None:
            actions = list(self.fallback(context, execution_steps))
            if len(actions) != execution_steps:
                raise ValueError(
                    f"fallback returned {len(actions)} actions, "
                    f"expected {execution_steps}"
                )
            for index, action in enumerate(actions):
                if not isinstance(action, int) or not 0 <= action < len(
                    self.action_levels
                ):
                    raise ValueError(
                        f"fallback action {index} is not a valid action index"
                    )
            return actions

        zero = level_to_index(0.0, self.action_levels)
        if zero is None:
            raise RuntimeError("action levels must include 0.0 for the hold fallback")
        return [zero] * execution_steps
