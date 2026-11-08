"""Deterministic stubs for agent tests and CI (no API key required)."""

from __future__ import annotations

import json
import re

from .llm import LLMResponse


class StubLLMClient:
    """Return a fixed valid schedule, adapting to the requested window length."""

    def __init__(self, level: float = 0.0):
        self.level = level

    def complete(
        self, messages: list[dict], *, tools: list[dict] | None = None
    ) -> LLMResponse:
        steps = 16
        for message in reversed(messages):
            if message.get("role") != "user":
                continue
            match = re.search(r"execution_steps:\s*(\d+)", message.get("content", ""))
            if match:
                steps = int(match.group(1))
                break
        payload = {
            "schedule": [
                {"interval": index, "level": self.level} for index in range(steps)
            ],
            "rationale": "stub schedule",
            "confidence": 80,
        }
        return LLMResponse(
            content=json.dumps(payload),
            prompt_tokens=10,
            completion_tokens=10,
            latency_s=0.0,
            model="stub",
        )


class StubSimulator:
    """Deterministic simulator used until lane B's env/runner is available."""

    def simulate(
        self, context: dict, actions: list[int], execution_steps: int
    ) -> dict:
        soc = float(context.get("battery", {}).get("soc", 0.5))
        return {
            "net_cost_ron": 0.0,
            "import_cost_ron": 0.0,
            "export_revenue_ron": 0.0,
            "soc_trajectory": [soc] * execution_steps,
            "feasible": True,
            "violations_mwh": 0.0,
            "curtailed_mwh": 0.0,
            "degradation_ron": 0.0,
            "actions": list(actions),
        }
