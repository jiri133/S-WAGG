"""ENTSO-E national load ingestion.

The delivered CSV (``ENTSO_15MIN.csv``) has one row per 15-minute MTU with the
label in **CET/CEST**, not Europe/Bucharest local time::

    "01/01/2026 00:00 - 01/01/2026 00:15", "BZN|RO", "5788.00", "5790.00"

Ambiguous / nonexistent transition intervals carry an explicit ``(CET)`` or
``(CEST)`` suffix, e.g. on the fall-back day both ``02:30 (CEST)`` and
``02:30 (CET)`` appear.  The parser converts every label to a UTC instant so
the series can be joined with OPCOM prices (which are stored in UTC).

Missing values are the literal ``-`` and are returned as ``None``; the caller
decides whether an interval is complete.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from .opcom import is_eest

STEP = timedelta(minutes=15)
DEFAULT_AREA = "BZN|RO"

#: ``DD/MM/YYYY HH:MM`` with an optional CET/CEST marker on transition days.
MTU_RE = re.compile(
    r"^(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4}) "
    r"(?P<hour>\d{2}):(?P<minute>\d{2})"
    r"(?: \((?P<tz>CET|CEST)\))?$"
)


class EntsoParseError(ValueError):
    """Raised when an ENTSO-E CSV does not match the expected shape."""


@dataclass(frozen=True)
class EntsoRow:
    """One 15-minute national load interval."""

    timestamp_utc: datetime
    load_mw: float | None
    load_forecast_mw: float | None
    raw_mtu: str

    @property
    def is_complete(self) -> bool:
        return self.load_mw is not None and self.load_forecast_mw is not None


def _optional_float(value: str) -> float | None:
    text = (value or "").strip().strip('"')
    if text.upper() in {"", "-", "N/A", "NA"}:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise EntsoParseError(f"not a number: {value!r}") from exc


def _clean(value: str) -> str:
    return (value or "").strip().strip('"')


def parse_mtu_label(label: str) -> datetime:
    """Convert one ENTSO-E MTU start label (CET/CEST) to an aware UTC datetime.

    When no suffix is present the offset is inferred from Romania's EU DST
    window.  The DST window in UTC is identical for CET/CEST and EET/EEST, so
    ``opcom.is_eest`` is reused rather than duplicating the rule.
    """

    match = MTU_RE.match(_clean(label))
    if match is None:
        raise EntsoParseError(f"unrecognised MTU label: {label!r}")

    naive = datetime(
        int(match["year"]),
        int(match["month"]),
        int(match["day"]),
        int(match["hour"]),
        int(match["minute"]),
    )
    marker = match["tz"]
    if marker == "CET":
        offset = timedelta(hours=1)
    elif marker == "CEST":
        offset = timedelta(hours=2)
    else:
        # Try the summer interpretation first; if that UTC instant is outside
        # the DST window the label must be CET.
        candidate = (naive - timedelta(hours=2)).replace(tzinfo=UTC)
        offset = timedelta(hours=2) if is_eest(candidate) else timedelta(hours=1)
    return (naive - offset).replace(tzinfo=UTC)


def parse_entsoe_csv(
    path: str | Path,
    *,
    area: str = DEFAULT_AREA,
    validate: bool = True,
) -> list[EntsoRow]:
    """Parse one ENTSO-E export, keeping only ``area`` rows.

    ``validate`` enforces a continuous 15-minute UTC sequence with no
    duplicate instants.  Disable it for hand-built test fixtures.
    """

    target = Path(path)
    rows: list[EntsoRow] = []
    with target.open(encoding="utf-8-sig", newline="") as fh:
        for raw in csv.reader(fh):
            if not raw or not raw[0].strip():
                continue
            label = _clean(raw[0])
            if label.startswith("MTU") or label.lower() == "mtu (cet/cest)":
                continue
            if len(raw) < 4:
                raise EntsoParseError(f"{target.name}: malformed row {raw!r}")
            if _clean(raw[1]) != area:
                continue

            start_label, separator, end_label = label.partition(" - ")
            if not separator:
                raise EntsoParseError(f"{target.name}: malformed MTU range {raw[0]!r}")
            start = parse_mtu_label(start_label)
            end = parse_mtu_label(end_label)
            if end - start != STEP:
                raise EntsoParseError(
                    f"{target.name}: MTU {raw[0]!r} spans {end - start}, expected 15 minutes"
                )
            rows.append(
                EntsoRow(
                    timestamp_utc=start,
                    load_mw=_optional_float(raw[2]),
                    load_forecast_mw=_optional_float(raw[3]),
                    raw_mtu=label,
                )
            )

    if not rows:
        raise EntsoParseError(f"{target.name}: no rows for area {area!r}")
    rows.sort(key=lambda row: row.timestamp_utc)
    if validate:
        validate_continuity(rows)
    return rows


def validate_continuity(rows: list[EntsoRow]) -> None:
    """Require a strictly increasing, gapless 15-minute UTC sequence."""

    seen: set[datetime] = set()
    previous: datetime | None = None
    for row in rows:
        if row.timestamp_utc in seen:
            raise EntsoParseError(f"duplicate timestamp {row.timestamp_utc.isoformat()}")
        seen.add(row.timestamp_utc)
        if previous is not None and row.timestamp_utc - previous != STEP:
            raise EntsoParseError(
                f"irregular step {previous.isoformat()} -> {row.timestamp_utc.isoformat()}"
            )
        previous = row.timestamp_utc


def to_frame(rows: list[EntsoRow]) -> pd.DataFrame:
    """Convert parsed rows to a UTC-indexed DataFrame."""

    frame = pd.DataFrame(
        {
            "timestamp_utc": [row.timestamp_utc for row in rows],
            "load_mw": [row.load_mw for row in rows],
            "load_forecast_mw": [row.load_forecast_mw for row in rows],
            "is_complete": [row.is_complete for row in rows],
        }
    )
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    return frame


def load_entsoe_frame(path: str | Path, *, area: str = DEFAULT_AREA) -> pd.DataFrame:
    """Parse an ENTSO-E CSV into a DataFrame with a ``timestamp_utc`` column."""

    return to_frame(parse_entsoe_csv(path, area=area))
