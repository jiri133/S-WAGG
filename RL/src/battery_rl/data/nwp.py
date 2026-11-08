"""Causal NWP forecasts from Open-Meteo's Single Runs API.

The receding horizon re-plans at local 00/04/08/12/16/20.  To keep the
features causal we need the NWP forecast that was **available at that issue
time**, not the final analysis.  Open-Meteo's Single Runs API exposes the
original model runs (ECMWF IFS HRES at 00/06/12/18 UTC) with their exact
initialisation time, so each 4-hour issue is mapped to the latest run whose
output would have been available after a conservative publication lag.

The Historical Forecast API is a stitched continuous series and does not
preserve run initialisation times, so it is *not* used for training.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

LOGGER = logging.getLogger("battery_rl.data.nwp")

SINGLE_RUNS_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
USER_AGENT = "battery-rl-research"

RUN_FREQUENCY_HOURS = 6
ARCHIVE_START = datetime(2024, 3, 14, tzinfo=UTC)

#: API variable name -> model feature name.
NWP_VARIABLES: dict[str, str] = {
    "shortwave_radiation": "ghi",
    "direct_normal_irradiance": "dni",
    "diffuse_radiation": "dhi",
    "cloud_cover": "cloud_cover",
    "temperature_2m": "temperature",
    "relative_humidity_2m": "humidity",
    "wind_speed_10m": "wind_speed",
    "precipitation": "precipitation",
    "snow_depth": "snow",
}
NWP_FEATURES = list(NWP_VARIABLES.values())


class NWPFetchError(RuntimeError):
    """Raised when an NWP run or aerosol series cannot be fetched."""


def _fetch_json(url: str, *, timeout: float, retries: int = 3) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read()[:300].decode("utf-8", "replace")
            except Exception:  # pragma: no cover - best effort
                pass
            if exc.code == 400:
                # An unavailable run will not become available by retrying.
                raise NWPFetchError(f"HTTP 400 for {url}: {detail}") from exc
            last_error = NWPFetchError(f"HTTP {exc.code} for {url}: {detail}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = NWPFetchError(f"could not fetch {url}: {exc}")
        if attempt < retries:
            time.sleep(min(2**attempt * 0.5, 8.0))
    raise last_error or NWPFetchError(f"could not fetch {url}")


def latest_run(issue_utc: datetime, lag_hours: float = 6.0) -> datetime:
    """Latest 6-hour UTC model run likely published by ``issue_utc``.

    A global model's 00 UTC run is typically available after 04-06 UTC, so a
    6-hour publication lag is the conservative default.  The returned run is
    floored to the previous 00/06/12/18 UTC cycle.
    """

    issue = pd.Timestamp(issue_utc).tz_convert("UTC").to_pydatetime()
    available_by = issue - timedelta(hours=lag_hours)
    hour = (available_by.hour // RUN_FREQUENCY_HOURS) * RUN_FREQUENCY_HOURS
    run = available_by.replace(hour=hour, minute=0, second=0, microsecond=0)
    if run < ARCHIVE_START:
        raise NWPFetchError(
            f"issue {issue.isoformat()} precedes the Single Runs archive "
            f"({ARCHIVE_START.isoformat()})"
        )
    return run


class SingleRunNWP:
    """Fetch and cache one Open-Meteo model run per 00/06/12/18 UTC cycle."""

    name = "open-meteo-single-runs"

    def __init__(
        self,
        latitude: float,
        longitude: float,
        cache_dir: str | Path,
        *,
        model: str = "ecmwf_ifs",
        run_lag_hours: float = 6.0,
        forecast_hours: int = 48,
        timeout: float = 60.0,
        max_workers: int = 4,
        max_run_fallbacks: int = 8,
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.cache_dir = Path(cache_dir)
        self.model = model
        self.run_lag_hours = run_lag_hours
        self.forecast_hours = forecast_hours
        self.timeout = timeout
        self.max_workers = max(1, max_workers)
        self.max_run_fallbacks = max(0, max_run_fallbacks)

    def run_for_issue(self, issue_utc: datetime) -> datetime:
        return latest_run(issue_utc, self.run_lag_hours)

    def payload(self, run: datetime) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "run": run.strftime("%Y-%m-%dT%H:%M"),
            "hourly": ",".join(NWP_VARIABLES),
            "models": self.model,
            "forecast_hours": self.forecast_hours,
            "timezone": "UTC",
        }

    def cache_path(self, run: datetime) -> Path:
        return self.cache_dir / f"{self.model}_{run:%Y%m%dT%H%M}.json"

    def _write_cache(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_text(json.dumps(data) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _load_or_fetch(self, run: datetime) -> dict:
        """Load a run, falling back to older runs if the archive has a gap."""

        cache = self.cache_path(run)
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))

        last_error: Exception | None = None
        for attempt in range(self.max_run_fallbacks + 1):
            candidate = run - timedelta(hours=RUN_FREQUENCY_HOURS * attempt)
            if candidate < ARCHIVE_START:
                break
            candidate_cache = self.cache_path(candidate)
            if candidate_cache.exists():
                data = json.loads(candidate_cache.read_text(encoding="utf-8"))
                data["_run_used"] = candidate.isoformat()
                self._write_cache(cache, data)
                return data
            query = urllib.parse.urlencode(self.payload(candidate))
            try:
                data = _fetch_json(f"{SINGLE_RUNS_URL}?{query}", timeout=self.timeout)
            except NWPFetchError as exc:
                last_error = exc
                if "not available" not in str(exc).lower():
                    raise
                LOGGER.debug(
                    "run %s unavailable; trying %s",
                    candidate,
                    candidate - timedelta(hours=RUN_FREQUENCY_HOURS),
                )
                continue
            data["_run_used"] = candidate.isoformat()
            self._write_cache(cache, data)
            return data
        raise NWPFetchError(
            f"no available {self.model} run at or before {run.isoformat()} "
            f"within {self.max_run_fallbacks} fallbacks"
        ) from last_error

    def frame_for_run(self, run: datetime) -> pd.DataFrame:
        """Hourly NWP frame for one run, indexed by valid UTC time."""

        data = self._load_or_fetch(run)
        hourly = data.get("hourly")
        if not isinstance(hourly, dict) or "time" not in hourly:
            raise NWPFetchError(f"run {run.isoformat()} has no hourly block")
        index = pd.to_datetime(hourly["time"], utc=True, format="ISO8601")
        frame = pd.DataFrame(index=index)
        for feature in NWP_VARIABLES.values():
            frame[feature] = 0.0
        for api_name, feature in NWP_VARIABLES.items():
            if api_name in hourly:
                frame[feature] = pd.to_numeric(hourly[api_name], errors="coerce")
        frame = frame.sort_index()
        frame = frame[~frame.index.duplicated(keep="first")]
        return frame.interpolate(method="time", limit_direction="both").fillna(0.0)

    def frame_for_issue(
        self, issue_utc: datetime, timestamps: pd.DatetimeIndex
    ) -> pd.DataFrame:
        """NWP features at ``timestamps`` from the run available at the issue."""

        index = pd.DatetimeIndex(timestamps).tz_convert("UTC")
        run = self.run_for_issue(issue_utc)
        frame = self.frame_for_run(run)
        union = frame.index.union(index)
        filled = frame.reindex(union).interpolate(method="time", limit_direction="both")
        return filled.reindex(index).fillna(0.0)

    def prefetch(self, issues: Iterable[datetime]) -> None:
        """Fetch every required run once, in parallel, with caching."""

        runs = sorted({self.run_for_issue(issue) for issue in issues})
        missing = [run for run in runs if not self.cache_path(run).exists()]
        if not missing:
            LOGGER.debug("NWP cache already covers %d runs", len(runs))
            return
        LOGGER.info("fetching %d NWP runs (%d cached)", len(missing), len(runs) - len(missing))
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            for done, _ in enumerate(pool.map(self.frame_for_run, missing), start=1):
                if done % 25 == 0 or done == len(missing):
                    LOGGER.info("NWP runs fetched: %d/%d", done, len(missing))

    def metadata(self) -> dict:
        return {
            "source": self.name,
            "model": self.model,
            "run_lag_hours": self.run_lag_hours,
            "runs_utc": [0, 6, 12, 18],
            "forecast_hours": self.forecast_hours,
            "url": SINGLE_RUNS_URL,
            "cache_dir": str(self.cache_dir),
        }


def fetch_aerosol(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    cache_dir: str | Path,
    *,
    timeout: float = 90.0,
) -> pd.Series:
    """Hourly aerosol optical depth from the Open-Meteo air-quality archive."""

    payload = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": "aerosol_optical_depth",
        "timezone": "UTC",
    }
    directory = Path(cache_dir)
    query = urllib.parse.urlencode(payload)
    cache = directory / f"aerosol_{start.isoformat()}_{end.isoformat()}.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        data = _fetch_json(f"{AIR_QUALITY_URL}?{query}", timeout=timeout)
        directory.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(cache.suffix + ".part")
        tmp.write_text(json.dumps(data) + "\n", encoding="utf-8")
        tmp.replace(cache)
    hourly = data.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise NWPFetchError("air-quality response has no hourly block")
    index = pd.to_datetime(hourly["time"], utc=True, format="ISO8601")
    values = pd.to_numeric(hourly.get("aerosol_optical_depth"), errors="coerce")
    series = pd.Series(values, index=index, name="aerosol").sort_index()
    series = series[~series.index.duplicated(keep="first")]
    return series.interpolate(method="time", limit_direction="both").fillna(0.0)
