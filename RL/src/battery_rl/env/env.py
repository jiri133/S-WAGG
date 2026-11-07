"""Simulator environment: ``reset(day)`` / ``step(action)`` over one delivery day.

The environment composes the battery physics (``env.battery``) and the grid balance
(``env.balance``) and exposes the frozen per-step ``info`` contract from
``TEAM_PLAN.md`` section 3.4.  It is not a Gym ``Env``: the agent sees the versioned JSON
context from ``env.context``, not a normalized observation vector.

The site is a merchant PV + battery asset with **zero local demand**
(``TEAM_PLAN.md`` section 3.1): PV and battery discharge are exported, grid charging is
imported, and ``load_mw`` is national market context only, never a balance demand.

Sign convention: a positive action level discharges/sells, a negative level charges/buys,
and action indices ``0..16`` map to ``agents.schemas.ACTION_LEVELS``.
"""

from __future__ import annotations

import operator
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import numpy as np

from battery_rl.agents.schemas import ACTION_COUNT, ACTION_LEVELS, index_to_level
from battery_rl.config import EnvConfig, FarmConfig
from battery_rl.data.dataset import DayData
from battery_rl.data.opcom import STEP, local_midnight_utc
from battery_rl.env.balance import solve_balance
from battery_rl.env.battery import Battery, BatterySpec

INFO_KEYS = frozenset(
    {
        "timestamp_utc",
        "step_index",
        "pv_mw",
        "load_mw",
        "price_ron_mwh",
        "soc",
        "soc_next",
        "p_charge_mw",
        "p_discharge_mw",
        "requested_level",
        "executed_level",
        "import_mw",
        "export_mw",
        "curtailed_mw",
        "cost_ron",
        "degradation_ron",
        "violation_mwh",
        "feasible",
    }
)
"""The exact per-step ``info`` keys; do not rename or add to this in the environment."""

SITE_DEMAND_MW = 0.0
"""The merchant site has no local demand; national load is context only (TEAM_PLAN 3.1)."""


@dataclass(frozen=True)
class EnvState:
    """The state visible at a decision point."""

    day: date
    step_index: int
    steps_remaining: int
    timestamp_utc: datetime
    soc: float
    energy_mwh: float


@dataclass(frozen=True)
class EnvStep:
    """One environment step: the contract ``info`` plus scoring and termination flags."""

    info: dict[str, Any]
    score_ron: float
    terminated: bool
    truncated: bool
    state: EnvState


class BatteryEnv:
    """Stateful day simulator.

    ``days`` may be one ``DayData``, a mapping keyed by delivery date, or an iterable of
    ``DayData``.  ``reset(day)`` selects one; if only one day is loaded, ``reset()`` is
    enough.  DST days keep their real 92/100 intervals.
    """

    def __init__(
        self,
        days: DayData | Mapping[date, DayData] | Iterable[DayData],
        spec: BatterySpec,
        config: EnvConfig,
        *,
        export_limit_mw: float | None = None,
        import_limit_mw: float | None = None,
    ) -> None:
        if list(config.action_levels) != list(ACTION_LEVELS):
            raise ValueError(
                "configs/env.yaml action_levels do not match the frozen 17-level contract"
            )
        dt_h = config.step_minutes / 60.0
        if abs(dt_h - STEP.total_seconds() / 3600.0) > 1e-12:
            raise ValueError(
                "step_minutes must match the 15-minute dataset resolution, "
                f"got {config.step_minutes}"
            )
        _validate_limit("export_limit_mw", export_limit_mw)
        _validate_limit("import_limit_mw", import_limit_mw)

        self.spec = spec
        self.config = config
        self.objective = config.objective
        self.dt_h = dt_h
        self.export_limit_mw = export_limit_mw
        self.import_limit_mw = import_limit_mw
        self._days = _normalize_days(days)

        self._day: DayData | None = None
        self._step_index = 0
        self._battery: Battery | None = None
        self._records: list[dict[str, Any]] = []
        self._total_cost_ron = 0.0
        self._total_degradation_ron = 0.0
        self._total_violation_penalty_ron = 0.0
        self._terminal_price_ron_mwh = 0.0

    @classmethod
    def from_farm(
        cls,
        days: DayData | Mapping[date, DayData] | Iterable[DayData],
        farm: FarmConfig,
        config: EnvConfig,
    ) -> BatteryEnv:
        """Build the scaled battery and grid limits from the active farm config."""
        return cls(
            days,
            BatterySpec.from_farm_config(farm),
            config,
            export_limit_mw=farm.grid.export_limit_mw,
            import_limit_mw=farm.grid.import_limit_mw,
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def day(self) -> DayData | None:
        return self._day

    @property
    def step_index(self) -> int:
        return self._step_index

    @property
    def steps_remaining(self) -> int:
        if self._day is None:
            return 0
        return max(0, self._day.intervals - self._step_index)

    @property
    def done(self) -> bool:
        return self._day is not None and self._step_index >= self._day.intervals

    @property
    def battery(self) -> Battery:
        if self._battery is None:
            raise RuntimeError("call reset() before reading the battery")
        return self._battery

    @property
    def soc(self) -> float:
        return self.battery.soc

    @property
    def energy_mwh(self) -> float:
        return self.battery.energy_mwh

    @property
    def current_time_utc(self) -> datetime:
        if self._day is None:
            raise RuntimeError("call reset() before reading the clock")
        return local_midnight_utc(self._day.day) + STEP * self._step_index

    @property
    def state(self) -> EnvState:
        if self._day is None:
            raise RuntimeError("call reset() before reading the state")
        return EnvState(
            day=self._day.day,
            step_index=self._step_index,
            steps_remaining=self.steps_remaining,
            timestamp_utc=self.current_time_utc,
            soc=self.soc,
            energy_mwh=self.energy_mwh,
        )

    @property
    def records(self) -> list[dict[str, Any]]:
        """Per-step ``info`` dicts since the last reset."""
        return list(self._records)

    @property
    def total_cost_ron(self) -> float:
        """Cash spent so far (negative means earned)."""
        return self._total_cost_ron

    @property
    def total_degradation_ron(self) -> float:
        return self._total_degradation_ron

    @property
    def total_violation_penalty_ron(self) -> float:
        return self._total_violation_penalty_ron

    @property
    def terminal_price_ron_mwh(self) -> float:
        """Reference price used to value the final stored energy."""
        return self._terminal_price_ron_mwh

    @property
    def episode_score_ron(self) -> float:
        """Objective from ``PLAN.md`` section 4, using the current SoC as the terminal SoC.

        Equivalent to ``-Σcost - Σdegradation - Σviolation_penalty + terminal_value``.
        On a completed day this is the day score; mid-day it is the partial score.
        """
        terminal = 0.0
        if self.objective.terminal_value_mode != "none" and self._battery is not None:
            terminal = self._terminal_price_ron_mwh * self._battery.energy_mwh * self.spec.eta_d
        return (
            -self._total_cost_ron
            - self._total_degradation_ron
            - self._total_violation_penalty_ron
            + terminal
        )

    # ------------------------------------------------------------------
    # Episode control
    # ------------------------------------------------------------------

    def reset(
        self,
        day: date | DayData | None = None,
        *,
        soc: float | None = None,
    ) -> EnvState:
        """Start a delivery day at the configured initial SoC (50% by default)."""
        selected = self._select_day(day)
        _validate_day(selected)
        self._day = selected
        self._step_index = 0
        self._battery = Battery(self.spec, self.config.initial_soc if soc is None else soc)
        self._records = []
        self._total_cost_ron = 0.0
        self._total_degradation_ron = 0.0
        self._total_violation_penalty_ron = 0.0
        self._terminal_price_ron_mwh = self._resolve_terminal_price(selected)
        return self.state

    def step(self, action: int) -> EnvStep:
        """Apply one action index and return the contract ``info`` for the interval."""
        if self._day is None or self._battery is None:
            raise RuntimeError("call reset() before step()")
        if self.done:
            raise RuntimeError("episode is finished; call reset()")

        action = _validate_action(action)
        day = self._day
        index = self._step_index
        requested_level = index_to_level(action)
        requested_mw = requested_level * self.spec.p_max_mw

        battery_step = self._battery.step(requested_mw, self.dt_h)
        balance = solve_balance(
            pv_mw=float(day.pv_mw[index]),
            demand_mw=SITE_DEMAND_MW,
            price_ron_mwh=float(day.price_ron_mwh[index]),
            battery_mw=battery_step.executed_mw,
            dt_h=self.dt_h,
            export_limit_mw=self.export_limit_mw,
            import_limit_mw=self.import_limit_mw,
        )
        degradation_ron = (
            self.objective.degradation_cost_ron_per_mwh * battery_step.throughput_mwh
        )
        violation_penalty_ron = (
            self.objective.violation_penalty_ron_per_mwh * battery_step.violation_mwh
        )

        info: dict[str, Any] = {
            "timestamp_utc": _iso_utc(self.current_time_utc),
            "step_index": index,
            "pv_mw": float(day.pv_mw[index]),
            # National market context; never the site's balance demand.
            "load_mw": float(day.load_mw[index]),
            "price_ron_mwh": float(day.price_ron_mwh[index]),
            "soc": battery_step.soc_before,
            "soc_next": battery_step.soc_after,
            "p_charge_mw": battery_step.charge_mw,
            "p_discharge_mw": battery_step.discharge_mw,
            "requested_level": requested_level,
            "executed_level": battery_step.executed_mw / self.spec.p_max_mw,
            "import_mw": balance.import_mw,
            "export_mw": balance.export_mw,
            "curtailed_mw": balance.curtailed_mw,
            "cost_ron": balance.cost_ron,
            "degradation_ron": degradation_ron,
            "violation_mwh": battery_step.violation_mwh,
            "feasible": battery_step.feasible,
        }

        self._records.append(info)
        self._total_cost_ron += balance.cost_ron
        self._total_degradation_ron += degradation_ron
        self._total_violation_penalty_ron += violation_penalty_ron
        self._step_index += 1

        return EnvStep(
            info=info,
            score_ron=-balance.cost_ron - degradation_ron - violation_penalty_ron,
            terminated=False,
            truncated=self.done,
            state=self.state,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _select_day(self, day: date | DayData | None) -> DayData:
        if day is None:
            if len(self._days) == 1:
                return next(iter(self._days.values()))
            raise ValueError("day is required when more than one delivery day is loaded")
        if isinstance(day, DayData):
            return day
        try:
            return self._days[day]
        except KeyError as exc:
            raise KeyError(
                f"day {day} is not loaded; available: {sorted(self._days)}"
            ) from exc

    def _resolve_terminal_price(self, day: DayData) -> float:
        mode = self.objective.terminal_value_mode
        if mode == "episode_mean_price":
            return float(np.mean(day.price_ron_mwh))
        if mode == "fixed":
            price = self.objective.terminal_reference_price_ron_per_mwh
            if price is None:
                raise ValueError(
                    "terminal_reference_price_ron_per_mwh is required when "
                    "terminal_value_mode='fixed'"
                )
            return float(price)
        return 0.0


def _normalize_days(
    days: DayData | Mapping[date, DayData] | Iterable[DayData],
) -> dict[date, DayData]:
    if isinstance(days, DayData):
        day_map = {days.day: days}
    elif isinstance(days, Mapping):
        day_map = dict(days)
    else:
        day_map = {}
        for item in days:
            if not isinstance(item, DayData):
                raise TypeError(f"expected DayData, got {type(item).__name__}")
            day_map[item.day] = item
    if not day_map:
        raise ValueError("at least one DayData is required")
    return day_map


def _validate_day(day: DayData) -> None:
    if day.intervals <= 0:
        raise ValueError(f"day.intervals must be positive, got {day.intervals}")
    series = {
        "price_ron_mwh": day.price_ron_mwh,
        "load_mw": day.load_mw,
        "load_forecast_mw": day.load_forecast_mw,
        "pv_mw": day.pv_mw,
        "pv_forecast_mw": day.pv_forecast_mw,
        "is_complete": day.is_complete,
    }
    for name, values in series.items():
        if len(values) != day.intervals:
            raise ValueError(
                f"{day.day}: {name} has {len(values)} values, expected {day.intervals}"
            )
    for name in ("price_ron_mwh", "load_mw", "load_forecast_mw", "pv_mw", "pv_forecast_mw"):
        values = np.asarray(series[name], dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError(f"{day.day}: {name} contains non-finite values")
    if len(day.pv_forecast_issue_utc) != day.intervals:
        raise ValueError(
            f"{day.day}: pv_forecast_issue_utc has {len(day.pv_forecast_issue_utc)} "
            f"values, expected {day.intervals}"
        )
    if not np.all(np.asarray(day.is_complete, dtype=bool)):
        raise ValueError(f"{day.day}: day contains incomplete intervals")
    for name in ("pv_mw", "pv_forecast_mw", "load_mw", "load_forecast_mw"):
        if np.any(np.asarray(series[name], dtype=float) < 0.0):
            raise ValueError(f"{day.day}: {name} contains negative values")


def _validate_action(action: int) -> int:
    if isinstance(action, bool):
        raise TypeError(f"action must be an int in 0..{ACTION_COUNT - 1}, got {action!r}")
    try:
        index = operator.index(action)
    except TypeError as exc:
        raise TypeError(
            f"action must be an int in 0..{ACTION_COUNT - 1}, got {action!r}"
        ) from exc
    if not 0 <= index < ACTION_COUNT:
        raise ValueError(f"action index must be in 0..{ACTION_COUNT - 1}, got {index}")
    return index


def _validate_limit(name: str, value: float | None) -> None:
    if value is not None and (not np.isfinite(value) or value <= 0.0):
        raise ValueError(f"{name} must be finite and positive when set, got {value}")


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
