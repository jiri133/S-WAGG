"""Frozen agent contracts: context JSON, schedule JSON and action levels.

Dev B owns this module; Dev A consumes it.  The shapes follow ``TEAM_PLAN.md`` section 3,
which is the source of truth when ``PLAN.md`` disagrees.

The context is the versioned JSON object the LLM sees at every four-hour decision point.
The schedule is the ``min(16, steps_remaining)``-entry plan it returns.  Both are validated
here so the LLM agent, the baselines, MPC, the oracle and the evaluator all speak exactly
the same language.

Do not change a field name or a length rule without a ``TEAM_PLAN.md`` PR and a message to
the other lane: these are the interfaces both lanes code against.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CONTEXT_VERSION: Literal["1"] = "1"
"""Version string carried in every context payload; bump with any shape change."""

STEP_MINUTES = 15
"""Length of one dispatch interval, matching ``configs/env.yaml``."""

STEP_HOURS = STEP_MINUTES / 60
"""Dispatch interval expressed in hours (0.25)."""

EXECUTION_STEPS = 16
"""Nominal schedule length: four hours of 15-minute intervals."""

ACTION_LEVELS: tuple[float, ...] = tuple(round(-1.0 + index * 0.125, 3) for index in range(17))
"""The 17 signed power levels; positive discharges/sells, negative charges/buys."""

ACTION_COUNT = len(ACTION_LEVELS)

LEVEL_TOLERANCE = 1e-9
"""Absolute tolerance used when matching a JSON float to one of the 17 levels."""

SOC_TOLERANCE = 1e-9
"""Absolute SoC tolerance when checking schedule feasibility."""

ENERGY_TOLERANCE_MWH = 1e-9
"""Absolute energy tolerance when checking schedule feasibility."""

MAX_SOC_ERRORS = 5
"""Cap on reported SoC violations so an LLM retry message stays readable."""


class _StrictModel(BaseModel):
    """Base model: no unknown keys and no NaN/inf anywhere in the payload."""

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )


class FarmContext(_StrictModel):
    """Identifying farm state shown to the agent (informational only)."""

    name: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    kwp: float = Field(gt=0)
    asset_scale: float = Field(gt=0)


class BatteryContext(_StrictModel):
    """Exact battery state and nameplate values at the decision point."""

    capacity_mwh: float = Field(gt=0)
    p_max_mw: float = Field(gt=0)
    soc: float = Field(ge=0, le=1)
    soc_min: float = Field(ge=0, le=1)
    soc_max: float = Field(ge=0, le=1)
    eta_c: float = Field(gt=0, le=1)
    eta_d: float = Field(gt=0, le=1)
    degradation_cost_ron_per_mwh: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_soc(self) -> BatteryContext:
        if self.soc_min >= self.soc_max:
            raise ValueError("soc_min must be strictly less than soc_max")
        if self.soc < self.soc_min - SOC_TOLERANCE or self.soc > self.soc_max + SOC_TOLERANCE:
            raise ValueError(
                f"soc must lie within [soc_min, soc_max] = "
                f"[{self.soc_min}, {self.soc_max}], got {self.soc}"
            )
        return self


class MarketContext(_StrictModel):
    """Delivery-day prices; the full day is supplied so the agent can plan ahead."""

    currency: str = Field(default="RON", min_length=1)
    prices_ron_mwh: list[float]


class PVContext(_StrictModel):
    """Current PV, the forecast for the rest of the day, and realized PV so far."""

    now_mw: float
    forecast_mw: list[float]
    realized_so_far_mw: list[float]


class LoadContext(_StrictModel):
    """Current national load and the day-ahead forecast for the rest of the day."""

    now_mw: float
    forecast_mw: list[float]


class LimitsContext(_StrictModel):
    """Optional grid connection limits; ``None`` means unlimited."""

    export_limit_mw: float | None = Field(default=None, gt=0)
    import_limit_mw: float | None = Field(default=None, gt=0)


class TerminalValue(_StrictModel):
    """How the remaining stored energy is valued at the end of the delivery day."""

    price_ron_mwh: float
    mode: Literal["episode_mean_price", "fixed", "none"]


class AgentContext(_StrictModel):
    """Versioned context JSON handed to every planner.

    Length rules (``TEAM_PLAN.md`` sections 3.2 and 3.3):

    - ``execution_steps == min(16, steps_remaining)``;
    - ``market.prices_ron_mwh`` covers the whole delivery day, i.e.
      ``step_index + steps_remaining`` entries (92/96/100 on DST days);
    - ``pv.forecast_mw`` and ``load.forecast_mw`` cover ``steps_remaining``;
    - ``pv.realized_so_far_mw`` covers ``step_index``;
    - ``previous_plan`` has at most 16 entries (empty before the first decision; on DST
      days the previous block can be longer than the current ``execution_steps``).
    """

    context_version: Literal["1"] = CONTEXT_VERSION
    delivery_day: date
    farm: FarmContext
    time_utc: datetime
    step_index: int = Field(ge=0)
    steps_remaining: int = Field(gt=0)
    execution_steps: int = Field(gt=0, le=EXECUTION_STEPS)
    battery: BatteryContext
    market: MarketContext
    pv: PVContext
    load: LoadContext
    limits: LimitsContext = Field(default_factory=LimitsContext)
    terminal_value: TerminalValue
    previous_plan: list[int] = Field(default_factory=list)

    @field_validator("time_utc")
    @classmethod
    def _normalize_time_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("time_utc must be timezone-aware (ISO 8601 with offset or Z)")
        return value.astimezone(UTC)

    @field_validator("previous_plan")
    @classmethod
    def _check_previous_plan_values(cls, value: list[int]) -> list[int]:
        for position, index in enumerate(value):
            if not 0 <= index < ACTION_COUNT:
                raise ValueError(
                    f"previous_plan[{position}] must be an action index "
                    f"0..{ACTION_COUNT - 1}, got {index}"
                )
        return value

    @model_validator(mode="after")
    def _check_lengths(self) -> AgentContext:
        expected_execution = min(EXECUTION_STEPS, self.steps_remaining)
        if self.execution_steps != expected_execution:
            raise ValueError(
                f"execution_steps must be min({EXECUTION_STEPS}, steps_remaining) = "
                f"{expected_execution}, got {self.execution_steps}"
            )

        day_intervals = self.step_index + self.steps_remaining
        price_count = len(self.market.prices_ron_mwh)
        if price_count != day_intervals:
            raise ValueError(
                "market.prices_ron_mwh must cover the whole delivery day: "
                f"expected {day_intervals} entries (step_index + steps_remaining), "
                f"got {price_count}"
            )

        if len(self.pv.forecast_mw) != self.steps_remaining:
            raise ValueError(
                "pv.forecast_mw must have steps_remaining entries: "
                f"expected {self.steps_remaining}, got {len(self.pv.forecast_mw)}"
            )
        if len(self.pv.realized_so_far_mw) != self.step_index:
            raise ValueError(
                "pv.realized_so_far_mw must have step_index entries: "
                f"expected {self.step_index}, got {len(self.pv.realized_so_far_mw)}"
            )
        if len(self.load.forecast_mw) != self.steps_remaining:
            raise ValueError(
                "load.forecast_mw must have steps_remaining entries: "
                f"expected {self.steps_remaining}, got {len(self.load.forecast_mw)}"
            )
        if len(self.previous_plan) > EXECUTION_STEPS:
            raise ValueError(
                f"previous_plan may have at most {EXECUTION_STEPS} entries, "
                f"got {len(self.previous_plan)}"
            )
        return self


class ScheduleEntry(_StrictModel):
    """One interval of a proposed schedule."""

    interval: int = Field(ge=0)
    level: float

    @field_validator("level")
    @classmethod
    def _check_level(cls, value: float) -> float:
        for level in ACTION_LEVELS:
            if math.isclose(value, level, rel_tol=0.0, abs_tol=LEVEL_TOLERANCE):
                return level
        raise ValueError(
            f"level must be one of the {ACTION_COUNT} signed action levels, got {value}"
        )


class Schedule(_StrictModel):
    """Structured LLM output: one signed level per execution interval."""

    schedule: list[ScheduleEntry] = Field(min_length=1, max_length=EXECUTION_STEPS)
    rationale: str = ""

    @model_validator(mode="after")
    def _check_intervals(self) -> Schedule:
        for position, entry in enumerate(self.schedule):
            if entry.interval != position:
                raise ValueError(
                    f"schedule[{position}].interval must equal {position}, got {entry.interval}"
                )
        return self

    def action_indices(self) -> list[int]:
        """Map each signed level to its action index in ``0..16``."""
        return [level_to_index(entry.level) for entry in self.schedule]

    @classmethod
    def from_action_indices(
        cls, indices: Sequence[int], rationale: str = ""
    ) -> Schedule:
        """Build a schedule payload from the planner-protocol action indices."""
        return cls(
            schedule=[
                ScheduleEntry(interval=position, level=index_to_level(index))
                for position, index in enumerate(indices)
            ],
            rationale=rationale,
        )

    def soc_errors(self, battery: BatteryContext) -> list[str]:
        """Return reasons this requested schedule leaves the SoC bounds.

        The trajectory is simulated with the same battery equations as the environment.
        When a step would overshoot a bound, it is recorded and then clipped to that bound
        so later steps are judged from the state the plant could actually reach.
        """
        capacity = battery.capacity_mwh
        energy = battery.soc * capacity
        lower = battery.soc_min * capacity
        upper = battery.soc_max * capacity
        errors: list[str] = []

        for entry in self.schedule:
            requested_mw = entry.level * battery.p_max_mw
            if requested_mw >= 0.0:  # discharge
                energy -= requested_mw * STEP_HOURS / battery.eta_d
                if energy < lower - ENERGY_TOLERANCE_MWH:
                    errors.append(
                        f"interval {entry.interval}: discharging {requested_mw:.3f} MW "
                        f"would take SoC below soc_min "
                        f"({energy / capacity:.4f} < {battery.soc_min})"
                    )
                    energy = lower
            else:  # charge
                energy += -requested_mw * STEP_HOURS * battery.eta_c
                if energy > upper + ENERGY_TOLERANCE_MWH:
                    errors.append(
                        f"interval {entry.interval}: charging {-requested_mw:.3f} MW "
                        f"would take SoC above soc_max "
                        f"({energy / capacity:.4f} > {battery.soc_max})"
                    )
                    energy = upper

        if len(errors) > MAX_SOC_ERRORS:
            extra = len(errors) - MAX_SOC_ERRORS
            errors = errors[:MAX_SOC_ERRORS]
            errors.append(f"... and {extra} more infeasible intervals")
        return errors


class ScheduleValidationError(ValueError):
    """A raw agent payload that violates the frozen schedule contract."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


def _format_validation_error(exc: ValidationError) -> list[str]:
    formatted: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "payload"
        formatted.append(f"{location}: {error['msg']}")
    return formatted


def index_to_level(index: int) -> float:
    """Return the signed level for action index ``0..16``."""
    if not 0 <= index < ACTION_COUNT:
        raise ValueError(f"action index must be in 0..{ACTION_COUNT - 1}, got {index}")
    return ACTION_LEVELS[index]


def level_to_index(level: float) -> int:
    """Return the action index for a signed level, tolerating JSON float noise."""
    for index, candidate in enumerate(ACTION_LEVELS):
        if math.isclose(level, candidate, rel_tol=0.0, abs_tol=LEVEL_TOLERANCE):
            return index
    raise ValueError(f"level must be one of the {ACTION_COUNT} signed levels, got {level}")


def action_power_mw(index: int, p_max_mw: float) -> float:
    """Convert an action index to signed power in MW (positive discharges/sells)."""
    if p_max_mw <= 0:
        raise ValueError(f"p_max_mw must be positive, got {p_max_mw}")
    return index_to_level(index) * p_max_mw


def validate_schedule(
    payload: object,
    context: AgentContext,
    *,
    check_soc: bool = True,
) -> list[str]:
    """Validate a raw agent payload against ``context``; return all violations.

    An empty list means the schedule is executable.  This is the function the LLM agent
    should call in its retry loop and count for ``llm_invalid_rate``.
    """
    if isinstance(payload, Schedule):
        schedule = payload
    else:
        try:
            schedule = Schedule.model_validate(payload)
        except ValidationError as exc:
            return _format_validation_error(exc)

    errors: list[str] = []
    if len(schedule.schedule) != context.execution_steps:
        errors.append(
            f"schedule length must equal execution_steps={context.execution_steps}, "
            f"got {len(schedule.schedule)}"
        )
    if check_soc:
        errors.extend(schedule.soc_errors(context.battery))
    return errors


def parse_schedule(
    payload: object,
    context: AgentContext,
    *,
    check_soc: bool = True,
) -> Schedule:
    """Validate and return a schedule, raising ``ScheduleValidationError`` on failure."""
    errors = validate_schedule(payload, context, check_soc=check_soc)
    if errors:
        raise ScheduleValidationError(errors)
    return payload if isinstance(payload, Schedule) else Schedule.model_validate(payload)
