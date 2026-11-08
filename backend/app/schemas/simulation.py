"""Schemas for the planning simulation endpoint."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SimulationStrategy = Literal[
    "llm",
    "mpc",
    "rule_based",
    "price_threshold",
    "idle",
    "oracle_lp",
]
SimulationSplit = Literal["train", "val", "test"]


class SimulationRequest(BaseModel):
    """Input for one planning run over a single delivery day."""

    model_config = ConfigDict(extra="forbid")

    strategy: SimulationStrategy = "llm"
    split: SimulationSplit = "val"
    # When omitted, the runner picks a random complete day from ``split``.
    day: date | None = None
    seed: int | None = Field(default=None, ge=0)


class SimulationDerate(BaseModel):
    """Production impact of the latest inspection, applied to the simulated PV."""

    mission_id: str | None
    month: int
    findings_total: int
    findings_counted: int
    findings_awaiting_review: int
    findings_rejected: int
    lost_kwh_day: float
    park_kwh_day: float
    factor: float


class SimulationResponse(BaseModel):
    """The runner's trace. Step/decision payloads stay permissive because the
    RL trace evolves with the evaluation contract; the top-level shape is fixed.
    """

    model_config = ConfigDict(extra="allow")

    day: str
    split: str
    strategy: str
    mode: str
    farm: dict[str, Any]
    summary: dict[str, Any]
    decisions: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    derate: SimulationDerate | None = None
