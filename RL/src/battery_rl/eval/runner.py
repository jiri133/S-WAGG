"""Evaluation runner: run per-step strategies and block planners over day splits.

The runner handles both frozen protocols (``StepStrategy.act`` and ``Planner.plan``),
variable 92/96/100-interval days, repeats, regime tagging and CSV export.  Regime
thresholds are computed from the evaluated split (daily mean price, price volatility and PV
energy terciles); a day may belong to several regimes, and ``all`` is added by the report.
"""

from __future__ import annotations

import csv
import operator
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date
from pathlib import Path
from typing import Any

import numpy as np

from battery_rl.agents.schemas import ACTION_COUNT
from battery_rl.config import EnvConfig, FarmConfig
from battery_rl.data.dataset import DayData
from battery_rl.env.battery import DEFAULT_STEP_HOURS
from battery_rl.env.context import build_context_dict
from battery_rl.env.env import BatteryEnv
from battery_rl.eval.metrics import (
    METRIC_NAMES,
    LLMTelemetry,
    MetricValue,
    compute_day_metrics,
)

REGIMES: tuple[str, ...] = (
    "high_price",
    "low_price",
    "volatile",
    "sunny",
    "cloudy",
    "weekend",
)
"""Data-derived regimes; the report also aggregates over ``all``."""

CSV_FIELDS: tuple[str, ...] = (
    "day",
    "strategy",
    "mode",
    "repeat",
    "score_ron",
    "regimes",
    *METRIC_NAMES,
)


@dataclass(frozen=True)
class StrategySpec:
    """One strategy factory plus the modes it should be evaluated in."""

    label: str
    factory: Callable[[DayData, BatteryEnv], Any]
    modes: tuple[str, ...] = ("block",)
    context_builder: Callable[..., dict[str, Any]] = build_context_dict


@dataclass(frozen=True)
class DayResult:
    """One strategy run on one delivery day."""

    day: date
    strategy: str
    mode: str
    repeat: int
    score_ron: float
    metrics: dict[str, MetricValue]
    regimes: tuple[str, ...]
    records: list[dict[str, Any]] = field(
        default_factory=list, repr=False, compare=False
    )


@dataclass(frozen=True)
class RegimeThresholds:
    """Split-level thresholds used to tag days."""

    price_low: float
    price_high: float
    volatility_high: float
    pv_low: float
    pv_high: float


def usable_days(days: Sequence[DayData]) -> list[DayData]:
    """Return the days whose ``is_complete`` mask has no missing contract interval."""
    return [day for day in days if bool(np.all(day.is_complete))]


def compute_regime_thresholds(
    days: Sequence[DayData], *, dt_h: float = DEFAULT_STEP_HOURS
) -> RegimeThresholds:
    """Tercile thresholds for price level, price volatility and daily PV energy."""
    if not days:
        raise ValueError("at least one delivery day is required")
    means = np.asarray([float(np.mean(day.price_ron_mwh)) for day in days])
    volatilities = np.asarray([float(np.std(day.price_ron_mwh)) for day in days])
    pv_energy = np.asarray([float(np.sum(day.pv_mw) * dt_h) for day in days])
    price_low, price_high = np.quantile(means, [1.0 / 3.0, 2.0 / 3.0])
    pv_low, pv_high = np.quantile(pv_energy, [1.0 / 3.0, 2.0 / 3.0])
    return RegimeThresholds(
        price_low=float(price_low),
        price_high=float(price_high),
        volatility_high=float(np.quantile(volatilities, 2.0 / 3.0)),
        pv_low=float(pv_low),
        pv_high=float(pv_high),
    )


def classify_day(
    day: DayData,
    thresholds: RegimeThresholds,
    *,
    dt_h: float = DEFAULT_STEP_HOURS,
) -> tuple[str, ...]:
    """Return the regimes this delivery day belongs to."""
    price_mean = float(np.mean(day.price_ron_mwh))
    price_volatility = float(np.std(day.price_ron_mwh))
    pv_energy = float(np.sum(day.pv_mw) * dt_h)
    tags: list[str] = []
    if price_mean <= thresholds.price_low:
        tags.append("low_price")
    if price_mean >= thresholds.price_high:
        tags.append("high_price")
    if price_volatility >= thresholds.volatility_high:
        tags.append("volatile")
    if pv_energy <= thresholds.pv_low:
        tags.append("cloudy")
    if pv_energy >= thresholds.pv_high:
        tags.append("sunny")
    if day.day.weekday() >= 5:
        tags.append("weekend")
    return tuple(tag for tag in REGIMES if tag in tags)


def state_info(env: BatteryEnv) -> dict[str, Any]:
    """Pre-step state passed to a ``StepStrategy``.

    The post-step ``info`` contract is produced by ``env.step``; per-step strategies need
    the current SoC and the interval's actual PV/price before acting.
    """
    day = env.day
    if day is None:
        raise RuntimeError("call env.reset() before reading the state")
    index = env.step_index
    return {
        "timestamp_utc": env.current_time_utc.astimezone(UTC).isoformat().replace(
            "+00:00", "Z"
        ),
        "step_index": index,
        "soc": env.soc,
        "energy_mwh": env.energy_mwh,
        "pv_mw": float(day.pv_mw[index]),
        "load_mw": float(day.load_mw[index]),
        "price_ron_mwh": float(day.price_ron_mwh[index]),
    }


def build_oracle_context(env: BatteryEnv, farm: FarmConfig) -> dict[str, Any]:
    """Context whose PV fields are the day's actuals, for the perfect-foresight oracle."""
    day = env.day
    if day is None:
        raise RuntimeError("call env.reset() before building a context")
    step_index = env.step_index
    context = build_context_dict(env, farm)
    context["pv"]["now_mw"] = float(day.pv_mw[step_index])
    context["pv"]["forecast_mw"] = [float(value) for value in day.pv_mw[step_index:]]
    context["pv"]["realized_so_far_mw"] = [
        float(value) for value in day.pv_mw[:step_index]
    ]
    return context


def run_day(
    env: BatteryEnv,
    strategy: Any,
    *,
    farm: FarmConfig,
    mode: str = "block",
    label: str | None = None,
    repeat: int = 0,
    regimes: Sequence[str] = (),
    context_builder: Callable[..., dict[str, Any]] = build_context_dict,
) -> DayResult:
    """Run one strategy over one delivery day and return its metrics."""
    if mode not in {"step", "block"}:
        raise ValueError(f"mode must be 'step' or 'block', got {mode!r}")
    env.reset()
    if mode == "step":
        _run_step(env, strategy)
    else:
        _run_block(env, strategy, farm, context_builder)

    llm = getattr(strategy, "telemetry", None)
    if llm is not None and not isinstance(llm, LLMTelemetry):
        raise TypeError("strategy.telemetry must be an LLMTelemetry or None")
    day = env.day
    if day is None:
        raise RuntimeError("environment did not reset")
    return DayResult(
        day=day.day,
        strategy=label or getattr(strategy, "name", type(strategy).__name__),
        mode=mode,
        repeat=repeat,
        score_ron=env.episode_score_ron,
        metrics=compute_day_metrics(env.records, env.spec, llm=llm),
        regimes=tuple(regimes),
        records=list(env.records),
    )


def run_split(
    days: Sequence[DayData],
    strategies: Sequence[StrategySpec],
    *,
    farm: FarmConfig,
    env_config: EnvConfig,
    repeats: int = 1,
    keep_records: bool = False,
    skip_incomplete: bool = True,
) -> list[DayResult]:
    """Run every strategy/mode/repeat over every day in the split.

    Incomplete days (``is_complete`` false on any interval) are skipped by default: the
    dataset marks known ENTSO-E gaps and the environment refuses to fabricate them.
    """
    if not days:
        raise ValueError("at least one delivery day is required")
    if not strategies:
        raise ValueError("at least one strategy is required")
    if repeats < 1:
        raise ValueError(f"repeats must be at least 1, got {repeats}")
    selected = usable_days(days) if skip_incomplete else list(days)
    if not selected:
        raise ValueError("no complete delivery days in the split")
    days = selected
    dt_h = env_config.step_minutes / 60.0
    thresholds = compute_regime_thresholds(days, dt_h=dt_h)

    results: list[DayResult] = []
    for day in days:
        regimes = classify_day(day, thresholds, dt_h=dt_h)
        for spec in strategies:
            if not spec.modes:
                raise ValueError(f"strategy {spec.label!r} has no modes")
            for mode in spec.modes:
                for repeat in range(repeats):
                    env = BatteryEnv.from_farm(day, farm, env_config)
                    strategy = spec.factory(day, env)
                    result = run_day(
                        env,
                        strategy,
                        farm=farm,
                        mode=mode,
                        label=spec.label,
                        repeat=repeat,
                        regimes=regimes,
                        context_builder=spec.context_builder,
                    )
                    if not keep_records:
                        result = replace(result, records=[])
                    results.append(result)
    return results


def to_rows(results: Sequence[DayResult]) -> list[dict[str, Any]]:
    """Flatten results for CSV/reporting."""
    rows: list[dict[str, Any]] = []
    for result in results:
        row: dict[str, Any] = {
            "day": result.day.isoformat(),
            "strategy": result.strategy,
            "mode": result.mode,
            "repeat": result.repeat,
            "score_ron": result.score_ron,
            "regimes": "|".join(result.regimes),
        }
        for name in METRIC_NAMES:
            row[name] = result.metrics[name]
        rows.append(row)
    return rows


def write_csv(results: Sequence[DayResult], path: str | Path) -> Path:
    """Write one row per strategy/day/repeat with the frozen metric columns."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(to_rows(results))
    return target


def _run_step(env: BatteryEnv, strategy: Any) -> None:
    if not hasattr(strategy, "act"):
        raise TypeError(f"{type(strategy).__name__} does not implement StepStrategy.act")
    while not env.done:
        action = _coerce_action(strategy.act(state_info(env)))
        env.step(action)


def _run_block(
    env: BatteryEnv,
    strategy: Any,
    farm: FarmConfig,
    context_builder: Callable[..., dict[str, Any]],
) -> None:
    if not hasattr(strategy, "plan"):
        raise TypeError(f"{type(strategy).__name__} does not implement Planner.plan")
    while not env.done:
        context = context_builder(env, farm)
        execution_steps = int(context["execution_steps"])
        plan = strategy.plan(context, execution_steps)
        if isinstance(plan, (str, bytes)) or not isinstance(plan, Sequence):
            raise TypeError("plan() must return a sequence of action indices")
        if len(plan) != execution_steps:
            raise ValueError(
                f"plan() returned {len(plan)} actions, expected {execution_steps}"
            )
        for action in plan:
            if env.done:
                raise ValueError("plan() returned more actions than the delivery day")
            env.step(_coerce_action(action))


def _coerce_action(action: Any) -> int:
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
