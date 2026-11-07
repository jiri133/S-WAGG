"""Aligned 15-minute dataset: contract, builder, loader and validator.

The frozen contract (TEAM_PLAN.md section 3.1) is one row per interval with::

    timestamp_utc, delivery_date, interval, price_ron_mwh,
    load_mw, load_forecast_mw, pv_mw, pv_forecast_mw,
    pv_forecast_issue_utc, is_complete

``delivery_date``/``interval`` come from OPCOM (Europe/Bucharest local day);
every other series is joined by ``timestamp_utc``.  DST days keep their real
92/96/100 intervals.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import RL_ROOT, EvalConfig
from .forecasts import attach_issue_times
from .opcom import STEP, expected_intervals, local_midnight_utc

DATASET_PATH = RL_ROOT / "artifacts/data/processed/aligned_2026.csv"
SPLITS_PATH = RL_ROOT / "artifacts/data/processed/splits.json"

ALIGNED_COLUMNS = [
    "timestamp_utc",
    "delivery_date",
    "interval",
    "price_ron_mwh",
    "load_mw",
    "load_forecast_mw",
    "pv_mw",
    "pv_forecast_mw",
    "pv_forecast_issue_utc",
    "is_complete",
]

UNITS = {
    "timestamp_utc": "ISO 8601 UTC",
    "delivery_date": "Europe/Bucharest local date",
    "interval": "1..N (N = 92, 96 or 100)",
    "price_ron_mwh": "RON/MWh",
    "load_mw": "MW",
    "load_forecast_mw": "MW",
    "pv_mw": "MW (scaled by farm asset_scale)",
    "pv_forecast_mw": "MW (scaled by farm asset_scale)",
    "pv_forecast_issue_utc": "ISO 8601 UTC",
    "is_complete": "bool",
}


class DatasetContractError(ValueError):
    """Raised when the aligned dataset violates the frozen contract."""


@dataclass(frozen=True)
class DayData:
    """One delivery day, ready for the environment.

    ``is_complete`` is an additive field: the frozen shape did not expose the
    per-interval gap flag, but consumers need it to decide whether a day is
    usable.  It is appended at the end so positional construction of the
    original fields still works.
    """

    day: date
    intervals: int
    price_ron_mwh: np.ndarray
    load_mw: np.ndarray
    load_forecast_mw: np.ndarray
    pv_mw: np.ndarray
    pv_forecast_mw: np.ndarray
    pv_forecast_issue_utc: list[str]
    is_complete: np.ndarray


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _dates(series: pd.Series) -> pd.Series:
    return series.map(lambda value: None if pd.isna(value) else _as_date(value))


def _range(series: pd.Series) -> dict[str, float | None]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {"min": None, "max": None}
    return {"min": float(values.min()), "max": float(values.max())}


def build_aligned(
    prices: pd.DataFrame,
    load: pd.DataFrame,
    pv_actual: pd.Series,
    forecast_model,
    *,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Join prices, national load and PV into the aligned contract.

    ``prices`` needs ``timestamp_utc, delivery_date, interval, price_ron_mwh``.
    ``load`` needs ``timestamp_utc, load_mw, load_forecast_mw``.
    ``pv_actual`` is a UTC-indexed ``pv_mw`` series (it may extend before the
    requested range so the persistence stub has history).
    """

    if end < start:
        raise DatasetContractError("end date must not be before start date")
    missing_prices = {"timestamp_utc", "delivery_date", "interval", "price_ron_mwh"} - set(
        prices.columns
    )
    if missing_prices:
        raise DatasetContractError(f"prices missing columns: {sorted(missing_prices)}")
    missing_load = {"timestamp_utc", "load_mw", "load_forecast_mw"} - set(load.columns)
    if missing_load:
        raise DatasetContractError(f"load missing columns: {sorted(missing_load)}")
    if pv_actual.index.has_duplicates:
        raise DatasetContractError("pv_actual index contains duplicates")
    if pv_actual.index.tz is None:
        raise DatasetContractError("pv_actual index must be timezone-aware UTC")

    if prices["delivery_date"].isna().any():
        raise DatasetContractError("prices contain a missing delivery_date")
    work = prices.copy()
    work["delivery_date"] = _dates(work["delivery_date"])
    work["timestamp_utc"] = pd.to_datetime(work["timestamp_utc"], utc=True)
    work = work[(work["delivery_date"] >= start) & (work["delivery_date"] <= end)]
    work = work.sort_values("timestamp_utc").reset_index(drop=True)
    if work["timestamp_utc"].duplicated().any():
        raise DatasetContractError("prices contain duplicate timestamps")
    if work.empty:
        raise DatasetContractError("no price rows in the requested date range")

    load_frame = load.copy()
    load_frame["timestamp_utc"] = pd.to_datetime(load_frame["timestamp_utc"], utc=True)
    load_frame = load_frame.drop_duplicates("timestamp_utc", keep="first")
    work = work.merge(
        load_frame[["timestamp_utc", "load_mw", "load_forecast_mw"]],
        on="timestamp_utc",
        how="left",
        validate="one_to_one",
    )
    work = attach_issue_times(work)

    timestamps = pd.DatetimeIndex(work["timestamp_utc"])
    pv_index = pv_actual.index.tz_convert("UTC")
    pv_series = pd.Series(pv_actual.to_numpy(dtype=float), index=pv_index).sort_index()
    work["pv_mw"] = pv_series.reindex(timestamps).to_numpy(dtype=float)
    forecast = forecast_model.forecast(pv_series, timestamps)
    work["pv_forecast_mw"] = pd.Series(forecast).reindex(timestamps).to_numpy(dtype=float)

    complete_fields = [
        "price_ron_mwh",
        "load_mw",
        "load_forecast_mw",
        "pv_mw",
        "pv_forecast_mw",
        "pv_forecast_issue_utc",
    ]
    work["is_complete"] = work[complete_fields].notna().all(axis=1)
    work = work.sort_values("timestamp_utc").reset_index(drop=True)
    return work[ALIGNED_COLUMNS]


def validate_aligned(frame: pd.DataFrame) -> dict:
    """Validate the contract and return a JSON-safe validation report."""

    missing = set(ALIGNED_COLUMNS) - set(frame.columns)
    if missing:
        raise DatasetContractError(f"missing columns: {sorted(missing)}")
    work = frame[ALIGNED_COLUMNS].copy()
    work["timestamp_utc"] = pd.to_datetime(work["timestamp_utc"], utc=True)
    work["pv_forecast_issue_utc"] = pd.to_datetime(
        work["pv_forecast_issue_utc"], utc=True
    )
    work["delivery_date"] = _dates(work["delivery_date"])
    work["interval"] = pd.to_numeric(work["interval"], errors="raise").astype(int)

    if work["timestamp_utc"].isna().any():
        raise DatasetContractError("timestamp_utc contains NaT")
    if work["delivery_date"].isna().any():
        raise DatasetContractError("delivery_date contains NaT")
    if work["is_complete"].isna().any():
        raise DatasetContractError("is_complete contains NA")
    if work["timestamp_utc"].duplicated().any():
        raise DatasetContractError("duplicate timestamp_utc")
    if (work["pv_forecast_issue_utc"] > work["timestamp_utc"]).any():
        raise DatasetContractError("pv_forecast_issue_utc is after its target")

    for day, group in work.groupby("delivery_date", sort=True):
        expected = expected_intervals(day)
        if len(group) != expected:
            raise DatasetContractError(
                f"{day.isoformat()}: {len(group)} intervals, expected {expected}"
            )
        ordered = group.sort_values("interval")
        intervals = ordered["interval"].tolist()
        if intervals != list(range(1, expected + 1)):
            raise DatasetContractError(f"{day.isoformat()}: intervals are not 1..{expected}")
        start_utc = local_midnight_utc(day)
        expected_times = [start_utc + STEP * (index - 1) for index in intervals]
        actual_times = [stamp.to_pydatetime() for stamp in ordered["timestamp_utc"]]
        if actual_times != expected_times:
            raise DatasetContractError(
                f"{day.isoformat()}: UTC timestamps do not match the local delivery day"
            )

    for column in ("load_mw", "load_forecast_mw", "pv_mw", "pv_forecast_mw"):
        values = pd.to_numeric(work[column], errors="coerce").dropna()
        if (values < 0).any():
            raise DatasetContractError(f"{column} contains negative values")

    expected_complete = work[
        [
            "price_ron_mwh",
            "load_mw",
            "load_forecast_mw",
            "pv_mw",
            "pv_forecast_mw",
            "pv_forecast_issue_utc",
        ]
    ].notna().all(axis=1)
    if not (work["is_complete"].astype(bool) == expected_complete).all():
        raise DatasetContractError("is_complete does not match the non-null fields")

    lag = (work["timestamp_utc"] - work["pv_forecast_issue_utc"]).dt.total_seconds() / 60.0
    interval_counts = Counter(
        int(count) for count in work.groupby("delivery_date").size().tolist()
    )
    dst_days = {
        day.isoformat(): expected_intervals(day)
        for day in sorted(work["delivery_date"].unique())
        if expected_intervals(day) != 96
    }
    return {
        "rows": int(len(work)),
        "days": int(work["delivery_date"].nunique()),
        "first_timestamp_utc": work["timestamp_utc"].min().isoformat(),
        "last_timestamp_utc": work["timestamp_utc"].max().isoformat(),
        "first_delivery_date": min(work["delivery_date"]).isoformat(),
        "last_delivery_date": max(work["delivery_date"]).isoformat(),
        "per_day_interval_counts": {
            str(key): value for key, value in sorted(interval_counts.items())
        },
        "dst_days": dst_days,
        "missing": {
            column: int(work[column].isna().sum())
            for column in (
                "price_ron_mwh",
                "load_mw",
                "load_forecast_mw",
                "pv_mw",
                "pv_forecast_mw",
                "pv_forecast_issue_utc",
            )
        },
        "incomplete_rows": int((~work["is_complete"].astype(bool)).sum()),
        "price_ron_mwh": _range(work["price_ron_mwh"]),
        "load_mw": _range(work["load_mw"]),
        "load_forecast_mw": _range(work["load_forecast_mw"]),
        "pv_mw": _range(work["pv_mw"]),
        "pv_forecast_mw": _range(work["pv_forecast_mw"]),
        "forecast_issue_lag_minutes": {
            "min": None if lag.dropna().empty else float(lag.min()),
            "max": None if lag.dropna().empty else float(lag.max()),
        },
    }


def write_aligned_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write the aligned CSV atomically with ISO-8601 UTC timestamps."""

    target = Path(path)
    output = frame[ALIGNED_COLUMNS].copy()
    output["timestamp_utc"] = [stamp.isoformat() for stamp in output["timestamp_utc"]]
    output["delivery_date"] = [day.isoformat() for day in output["delivery_date"]]
    output["pv_forecast_issue_utc"] = [
        stamp.isoformat() for stamp in output["pv_forecast_issue_utc"]
    ]
    output["is_complete"] = output["is_complete"].astype(bool)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    output.to_csv(tmp, index=False, lineterminator="\n", float_format="%.6f")
    tmp.replace(target)
    return target


def load_days(path: str | Path = DATASET_PATH, *, validate: bool = True) -> dict[date, DayData]:
    """Load the aligned CSV and group it into ``DayData`` objects."""

    frame = pd.read_csv(path)
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    frame["pv_forecast_issue_utc"] = pd.to_datetime(
        frame["pv_forecast_issue_utc"], utc=True
    )
    frame["delivery_date"] = _dates(frame["delivery_date"])
    frame["interval"] = frame["interval"].astype(int)
    frame["is_complete"] = frame["is_complete"].astype(bool)
    if validate:
        validate_aligned(frame)

    days: dict[date, DayData] = {}
    for day, group in frame.groupby("delivery_date", sort=True):
        ordered = group.sort_values("interval")
        days[day] = DayData(
            day=day,
            intervals=int(len(ordered)),
            price_ron_mwh=ordered["price_ron_mwh"].to_numpy(dtype=float),
            load_mw=ordered["load_mw"].to_numpy(dtype=float),
            load_forecast_mw=ordered["load_forecast_mw"].to_numpy(dtype=float),
            pv_mw=ordered["pv_mw"].to_numpy(dtype=float),
            pv_forecast_mw=ordered["pv_forecast_mw"].to_numpy(dtype=float),
            pv_forecast_issue_utc=[
                stamp.isoformat() for stamp in ordered["pv_forecast_issue_utc"]
            ],
            is_complete=ordered["is_complete"].to_numpy(dtype=bool),
        )
    return days


def load_split(
    split: str,
    *,
    dataset_path: str | Path = DATASET_PATH,
    splits_path: str | Path = SPLITS_PATH,
    validate: bool = True,
) -> list[DayData]:
    """Return the days in ``split`` (``train``, ``val`` or ``test``)."""

    splits = json.loads(Path(splits_path).read_text(encoding="utf-8"))
    if split not in splits:
        raise KeyError(f"unknown split {split!r}; available: {sorted(splits)}")
    start_raw, end_raw = splits[split]
    start = date.fromisoformat(str(start_raw))
    end = date.fromisoformat(str(end_raw))
    days = load_days(dataset_path, validate=validate)
    return [days[day] for day in sorted(days) if start <= day <= end]


def write_splits(eval_config: EvalConfig, path: str | Path = SPLITS_PATH) -> Path:
    """Write ``splits.json`` from the evaluation config."""

    train_start = eval_config.date_range.start
    train_end = eval_config.split.train_end
    val_start = train_end + timedelta(days=1)
    val_end = eval_config.split.val_end
    test_start = val_end + timedelta(days=1)
    test_end = eval_config.split.test_end
    payload = {
        "train": [train_start.isoformat(), train_end.isoformat()],
        "val": [val_start.isoformat(), val_end.isoformat()],
        "test": [test_start.isoformat(), test_end.isoformat()],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target
