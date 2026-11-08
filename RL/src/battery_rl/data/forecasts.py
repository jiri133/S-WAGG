"""Forecast issue times and the forecast-join contract.

The agent re-plans at local 00:00, 04:00, 08:00, 12:00, 16:00 and 20:00
Europe/Bucharest.  For every target interval the dataset records the latest
issue boundary at or before the target, so a consumer can verify that no
future information leaked into ``pv_forecast_mw``.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import UTC, date, datetime, time, timedelta

import pandas as pd

from .opcom import is_eest

#: Local Europe/Bucharest hours at which the agent may re-plan.
DECISION_LOCAL_HOURS: tuple[int, ...] = (0, 4, 8, 12, 16, 20)


class ForecastContractError(ValueError):
    """Raised when a forecast issue time is inconsistent with its target."""


def local_to_utc(naive: datetime) -> datetime:
    """Convert a naive Europe/Bucharest wall time to UTC.

    Romania is EET (UTC+2) in winter and EEST (UTC+3) in summer.  The only
    ambiguous wall-clock hour is the fall-back hour; the first occurrence
    (summer offset) is returned, which is what a delivery-day schedule uses.
    """

    if naive.tzinfo is not None:
        raise ValueError("local_to_utc expects a naive datetime")
    summer = (naive - timedelta(hours=3)).replace(tzinfo=UTC)
    if is_eest(summer):
        return summer
    winter = (naive - timedelta(hours=2)).replace(tzinfo=UTC)
    if not is_eest(winter):
        return winter
    return summer


def decision_boundaries_utc(day: date) -> list[datetime]:
    """The six UTC instants at which a delivery day may re-plan."""

    return [local_to_utc(datetime.combine(day, time(hour=hour))) for hour in DECISION_LOCAL_HOURS]


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def attach_issue_times(frame: pd.DataFrame) -> pd.DataFrame:
    """Add ``pv_forecast_issue_utc``: the latest boundary <= each timestamp."""

    required = {"timestamp_utc", "delivery_date"}
    missing = required - set(frame.columns)
    if missing:
        raise ForecastContractError(f"missing columns: {sorted(missing)}")

    result = frame.copy()
    result["timestamp_utc"] = pd.to_datetime(result["timestamp_utc"], utc=True)
    boundaries: dict[date, list[datetime]] = {}
    issue_times: list[datetime] = []

    for timestamp, raw_day in zip(
        result["timestamp_utc"], result["delivery_date"], strict=True
    ):
        day = _as_date(raw_day)
        if day not in boundaries:
            boundaries[day] = decision_boundaries_utc(day)
        candidates = boundaries[day]
        stamp = timestamp.to_pydatetime()
        index = bisect_right(candidates, stamp) - 1
        if index < 0:
            raise ForecastContractError(
                f"{stamp.isoformat()} precedes the first issue boundary of {day.isoformat()}"
            )
        issue_times.append(candidates[index])

    result["pv_forecast_issue_utc"] = pd.to_datetime(issue_times, utc=True)
    return result
