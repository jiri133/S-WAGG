"""Planner interfaces shared by the LLM agent, baselines, MPC and the evaluator.

Dev B owns this module; Dev A consumes it.  The protocol shapes are frozen in
``TEAM_PLAN.md`` section 3.5.  A planner receives the versioned context and returns one
action index per execution interval; a per-step strategy receives the latest ``info`` dict
and returns a single action index.

Action indices are ``0..16`` and map to ``agents.schemas.ACTION_LEVELS``; use
``agents.schemas.index_to_level`` / ``level_to_index`` to convert.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Planner(Protocol):
    """Block planner, replanned every four hours.

    ``context`` is the versioned context JSON produced by ``env.context`` (see
    ``agents.schemas.AgentContext``).  ``execution_steps`` is the number of action indices
    this decision must return: ``min(16, steps_remaining)``.
    """

    def plan(self, context: dict, execution_steps: int) -> list[int]:
        """Return ``execution_steps`` action indices for the next four hours."""
        ...


@runtime_checkable
class StepStrategy(Protocol):
    """Per-step strategy: map the latest environment ``info`` dict to one action index."""

    def act(self, info: dict) -> int:
        """Return one action index for the next 15-minute interval."""
        ...
