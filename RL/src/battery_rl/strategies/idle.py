"""Idle baseline: hold the battery at its current SoC for every interval."""

from __future__ import annotations

from battery_rl.strategies.common import HOLD_ACTION


class Idle:
    """The reference ``fără optimizare`` strategy: zero throughput, all PV exported."""

    name = "idle"

    def act(self, info: dict) -> int:
        return HOLD_ACTION

    def plan(self, context: dict, execution_steps: int = 16) -> list[int]:
        if execution_steps < 1:
            raise ValueError(f"execution_steps must be at least 1, got {execution_steps}")
        return [HOLD_ACTION] * execution_steps
