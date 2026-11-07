"""OPCOM PZU 15-minute price ingestion.

Source report page:
    https://www.opcom.ro/grafice-ip-raportPIP-si-volumTranzactionat/ro

Export endpoint:
    https://www.opcom.ro/rapoarte-pzu-raportPIP-export-csv/DD/MM/YYYY/ro?resolution=15

The CSV has a preamble (title + block averages), then one table with 96 rows for Romania.
DST transition days have 92 (spring) or 100 (fall) intervals. Interval 1 starts at local
midnight Europe/Bucharest and intervals are consecutive physical 15-minute slots, so the
UTC timestamp mapping only needs the UTC instant of local midnight.

Only the standard library is used, so the scraper runs without installing the RL package.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

LOGGER = logging.getLogger("battery_rl.data.opcom")

REPORT_URL = "https://www.opcom.ro/grafice-ip-raportPIP-si-volumTranzactionat/ro"
EXPORT_URL = (
    "https://www.opcom.ro/rapoarte-pzu-raportPIP-export-csv/"
    "{day:02d}/{month:02d}/{year:04d}/{lang}?resolution={resolution}"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "battery-rl-research"
)
UTC = timezone.utc
STEP = timedelta(minutes=15)
TITLE_DATE_RE = re.compile(r"ziua\s+de\s+livrare:\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE)

CSV_HEADERS = [
    "timestamp_utc",
    "delivery_date",
    "interval",
    "price_ron_mwh",
    "volume_mw",
    "buy_volume_mw",
    "sell_volume_mw",
    "resolution",
    "source_file",
    "source_url",
]


class FetchError(RuntimeError):
    """Raised when a download fails after all retries."""


class ParseError(ValueError):
    """Raised when a downloaded file does not match the expected schema."""


@dataclass(frozen=True)
class IntervalRow:
    timestamp_utc: datetime
    delivery_date: date
    interval: int
    price_ron_mwh: float
    volume_mw: float | None
    buy_volume_mw: float | None
    sell_volume_mw: float | None
    resolution: str
    source_file: str
    source_url: str


@dataclass(frozen=True)
class DayData:
    delivery_date: date
    intervals: int
    title_date: date | None
    rows: list[IntervalRow]


# ---------------------------------------------------------------------------
# DST handling (Europe/Bucharest, EU rules; no tzdata dependency)
# ---------------------------------------------------------------------------


def last_sunday(year: int, month: int) -> date:
    """Last Sunday of a month."""
    d = date(year, month, 31)
    return d - timedelta(days=(d.weekday() - 6) % 7)


def eest_bounds(year: int) -> tuple[datetime, datetime]:
    """UTC instants when EEST starts and ends (01:00 UTC on the transition Sundays)."""
    start = datetime.combine(last_sunday(year, 3), dtime(1, 0), tzinfo=UTC)
    end = datetime.combine(last_sunday(year, 10), dtime(1, 0), tzinfo=UTC)
    return start, end


def is_eest(utc_dt: datetime) -> bool:
    """True if the UTC instant falls in Romania's summer time (EEST, UTC+3)."""
    u = utc_dt.astimezone(UTC)
    start, end = eest_bounds(u.year)
    return start <= u < end


def local_midnight_utc(d: date) -> datetime:
    """UTC instant of 00:00 Europe/Bucharest on delivery date ``d``."""
    naive = datetime.combine(d, dtime(0, 0))
    # Local midnight is 21:00 or 22:00 UTC the previous day; midnight itself is never
    # ambiguous or nonexistent, so trying the summer offset first is sufficient.
    candidate = (naive - timedelta(hours=3)).replace(tzinfo=UTC)
    if is_eest(candidate):
        return candidate
    return (naive - timedelta(hours=2)).replace(tzinfo=UTC)


def expected_intervals(d: date) -> int:
    """Number of 15-minute intervals in the local delivery day (92/96/100)."""
    seconds = (local_midnight_utc(d + timedelta(days=1)) - local_midnight_utc(d)).total_seconds()
    return int(seconds // 900)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def export_url(d: date, resolution: int = 15, lang: str = "ro") -> str:
    return EXPORT_URL.format(
        day=d.day, month=d.month, year=d.year, lang=lang, resolution=resolution
    )


def raw_path(raw_dir: Path, d: date, resolution: int = 15) -> Path:
    return (
        raw_dir
        / f"{d.year:04d}"
        / f"{d.month:02d}"
        / f"{d.day:02d}"
        / f"rezultatePZU_PT{resolution}M_{d.isoformat()}.csv"
    )


def _fetch(url: str, *, timeout: float, retries: int) -> bytes | None:
    """Return body bytes, None for an empty (not yet published) day, raise FetchError."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*", "Referer": REPORT_URL},
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
            if not body:
                return None
            if b"Romania" not in body and b"PIP" not in body:
                raise FetchError(f"unexpected response body ({len(body)} bytes) from {url}")
            return body
        except (urllib.error.URLError, TimeoutError, FetchError) as exc:
            last_error = exc
            LOGGER.warning("fetch attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(min(2**attempt * 0.5, 10))
    raise FetchError(f"could not download {url}: {last_error}")


def download_day(
    d: date,
    raw_dir: Path,
    *,
    resolution: int = 15,
    overwrite: bool = False,
    timeout: float = 30.0,
    retries: int = 3,
) -> tuple[Path | None, str]:
    """Download one delivery day. Returns (path, status) or (None, 'no_data')."""
    path = raw_path(raw_dir, d, resolution)
    if path.exists() and not overwrite:
        return path, "cached"

    body = _fetch(export_url(d, resolution), timeout=timeout, retries=retries)
    if body is None:
        return None, "no_data"

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(body)
    tmp.replace(path)
    return path, "downloaded"


# ---------------------------------------------------------------------------
# Parse and validate
# ---------------------------------------------------------------------------


def _optional_float(value: str) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    return float(value)


def parse_day_csv(
    path: Path,
    delivery_date: date,
    source_label: str | None = None,
) -> DayData:
    """Parse one raw OPCOM CSV and validate intervals and timestamps."""
    label = source_label or str(path)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))

    title_date: date | None = None
    if rows and rows[0]:
        match = TITLE_DATE_RE.search(rows[0][0])
        if match:
            dd, mm, yyyy = (int(part) for part in match.groups())
            title_date = date(yyyy, mm, dd)

    header_index: int | None = None
    for index, row in enumerate(rows):
        if row and row[0].strip() == "Zona de tranzactionare":
            header_index = index
            break
    if header_index is None:
        raise ParseError(f"{path.name}: main table header not found")

    expected = expected_intervals(delivery_date)
    start_utc = local_midnight_utc(delivery_date)
    parsed: list[IntervalRow] = []

    for row in rows[header_index + 1 :]:
        if not row or row[0].strip() != "Romania":
            continue
        if len(row) < 7:
            raise ParseError(f"{path.name}: malformed Romania row {row!r}")
        interval = int(row[1])
        price = float(row[2])
        timestamp = start_utc + STEP * (interval - 1)
        parsed.append(
            IntervalRow(
                timestamp_utc=timestamp,
                delivery_date=delivery_date,
                interval=interval,
                price_ron_mwh=price,
                volume_mw=_optional_float(row[3]),
                buy_volume_mw=_optional_float(row[4]),
                sell_volume_mw=_optional_float(row[5]),
                resolution=row[6].strip(),
                source_file=label,
                source_url=export_url(delivery_date),
            )
        )

    if len(parsed) != expected:
        raise ParseError(
            f"{delivery_date.isoformat()}: expected {expected} intervals, got {len(parsed)}"
        )
    intervals = [item.interval for item in parsed]
    if intervals != list(range(1, expected + 1)):
        raise ParseError(f"{delivery_date.isoformat()}: interval numbers are not sequential")
    if title_date is not None and title_date != delivery_date:
        raise ParseError(
            f"{path.name}: title date {title_date.isoformat()} != {delivery_date.isoformat()}"
        )

    return DayData(
        delivery_date=delivery_date,
        intervals=expected,
        title_date=title_date,
        rows=parsed,
    )


# ---------------------------------------------------------------------------
# Range scrape
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_processed(rows: list[IntervalRow], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADERS)
        for row in rows:
            writer.writerow(
                [
                    row.timestamp_utc.isoformat(),
                    row.delivery_date.isoformat(),
                    row.interval,
                    row.price_ron_mwh,
                    "" if row.volume_mw is None else row.volume_mw,
                    "" if row.buy_volume_mw is None else row.buy_volume_mw,
                    "" if row.sell_volume_mw is None else row.sell_volume_mw,
                    row.resolution,
                    row.source_file,
                    row.source_url,
                ]
            )
    tmp.replace(output)


def scrape_range(
    start: date,
    end: date,
    *,
    raw_dir: Path,
    output: Path,
    resolution: int = 15,
    delay: float = 0.4,
    overwrite: bool = False,
    timeout: float = 30.0,
    retries: int = 3,
) -> dict:
    """Download and parse every delivery day in [start, end]."""
    if end < start:
        raise ValueError("end date must not be before start date")

    all_rows: list[IntervalRow] = []
    days: list[dict] = []
    failures: list[dict] = []
    totals = {"requested": 0, "downloaded": 0, "cached": 0, "no_data": 0, "parsed": 0}

    current = start
    while current <= end:
        totals["requested"] += 1
        url = export_url(current, resolution)
        entry: dict = {"date": current.isoformat(), "url": url}

        try:
            path, status = download_day(
                current,
                raw_dir,
                resolution=resolution,
                overwrite=overwrite,
                timeout=timeout,
                retries=retries,
            )
        except FetchError as exc:
            LOGGER.error("%s: %s", current.isoformat(), exc)
            failures.append({"date": current.isoformat(), "error": str(exc)})
            entry.update({"status": "fetch_failed", "error": str(exc)})
        else:
            if path is None:
                totals["no_data"] += 1
                entry["status"] = "no_data"
            else:
                totals[status] = totals.get(status, 0) + 1
                try:
                    parsed = parse_day_csv(
                        path, current, source_label=str(path.relative_to(raw_dir))
                    )
                except Exception as exc:  # one bad day must not abort the whole range
                    LOGGER.error("%s: %s", current.isoformat(), exc)
                    failures.append({"date": current.isoformat(), "error": str(exc)})
                    entry.update(
                        {
                            "status": "parse_failed",
                            "raw_file": str(path.relative_to(raw_dir)),
                            "error": str(exc),
                        }
                    )
                else:
                    all_rows.extend(parsed.rows)
                    totals["parsed"] += 1
                    entry.update(
                        {
                            "status": status,
                            "raw_file": str(path.relative_to(raw_dir)),
                            "bytes": path.stat().st_size,
                            "sha256": _sha256(path),
                            "intervals": parsed.intervals,
                        }
                    )

        days.append(entry)
        if delay > 0:
            time.sleep(delay)
        if totals["requested"] % 10 == 0 or current == end:
            LOGGER.info(
                "progress %s: %d/%d days, %d parsed, %d failures",
                current.isoformat(),
                totals["requested"],
                (end - start).days + 1,
                totals["parsed"],
                len(failures),
            )
        current += timedelta(days=1)

    all_rows.sort(key=lambda row: row.timestamp_utc)
    _write_processed(all_rows, output)

    manifest = {
        "source_page": REPORT_URL,
        "endpoint_template": EXPORT_URL,
        "resolution_minutes": resolution,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "delay_seconds": delay,
        "processed_csv": str(output),
        "totals": {
            **totals,
            "interval_rows": len(all_rows),
            "failures": len(failures),
        },
        "days": days,
        "failures": failures,
    }
    manifest_path = raw_dir / f"manifest_{start.isoformat()}_{end.isoformat()}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> int:
    today = date.today()
    default_end = min(today, date(2026, 12, 31))
    default_root = Path(__file__).resolve().parents[3]  # RL/

    parser = argparse.ArgumentParser(
        description="Download OPCOM PZU 15-minute prices for a date range."
    )
    parser.add_argument("--start", type=_parse_date, default=date(2026, 1, 1))
    parser.add_argument("--end", type=_parse_date, default=default_end)
    parser.add_argument("--resolution", type=int, choices=(15, 30, 60), default=15)
    parser.add_argument("--raw-dir", type=Path, default=default_root / "artifacts/data/raw/opcom")
    parser.add_argument(
        "--output",
        type=Path,
        default=default_root / "artifacts/data/processed/opcom_pzu_2026.csv",
    )
    parser.add_argument("--delay", type=float, default=0.4, help="seconds between requests")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--overwrite", action="store_true", help="re-download cached days")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    manifest = scrape_range(
        args.start,
        args.end,
        raw_dir=args.raw_dir,
        output=args.output,
        resolution=args.resolution,
        delay=args.delay,
        overwrite=args.overwrite,
        timeout=args.timeout,
        retries=args.retries,
    )
    print(json.dumps(manifest["totals"], indent=2))
    if manifest["failures"]:
        LOGGER.error("failures: %s", json.dumps(manifest["failures"], indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
