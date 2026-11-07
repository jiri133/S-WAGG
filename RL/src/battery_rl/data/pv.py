"""PV production sources for the aligned dataset.

The dataset needs one ``pv_mw`` value per 15-minute interval at the farm
coordinates.  Three interchangeable sources are provided:

``metered``
    A CSV supplied through ``farm.metered_pv_path`` (``timestamp_utc,pv_mw``
    or ``timestamp_utc,pv_kw``).  Preferred when real metered generation
    exists.

``open-meteo``
    Open-Meteo **archive** irradiance for the target period.  This is the
    default for 2026: PVGIS only serves 2005-2023, so it cannot provide a
    2026 actual series.  A fixed plane uses ``global_tilted_irradiance``; a
    dual-axis tracker uses ``direct_normal_irradiance`` + ``diffuse_radiation``
    with a simple plane-of-array model.

``pvgis``
    PVGIS ``seriescalc`` hourly output.  Only usable directly for 2005-2023;
    for a later target year the latest available year is used as a
    day-of-year proxy (recorded in the metadata as ``pvgis-YYYY-proxy``).

``clear-sky``
    Deterministic offline fallback.  It is clearly labelled and is only used
    when the caller explicitly asks for it (or passes ``--allow-fallback``).

All sources return a UTC-indexed ``pd.Series`` named ``pv_mw`` in MW, already
scaled by the farm ``asset_scale`` and clipped to the inverter AC rating.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol

import pandas as pd

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
USER_AGENT = "battery-rl-research"
PVGIS_MIN_YEAR = 2005
PVGIS_MAX_YEAR = 2023


class PVFetchError(RuntimeError):
    """Raised when an upstream PV/irradiance source cannot be fetched."""


class PVSource(Protocol):
    """Minimal source interface used by the dataset builder."""

    name: str

    def series(self, timestamps: pd.DatetimeIndex) -> pd.Series:
        """Return PV power in MW indexed by ``timestamps`` (UTC)."""


@dataclass(frozen=True)
class PVSpec:
    """Farm geometry needed to turn irradiance into PV power."""

    latitude: float
    longitude: float
    kwp: float
    inverter_ac_mw: float
    tilt_deg: float
    azimuth_deg: float  # 0=N, 90=E, 180=S, 270=W
    tracking: str = "none"
    asset_scale: float = 1.0
    performance_ratio: float = 0.85
    albedo: float = 0.20

    @property
    def scaled_kwp(self) -> float:
        return self.kwp * self.asset_scale

    @property
    def scaled_inverter_ac_mw(self) -> float:
        return self.inverter_ac_mw * self.asset_scale

    @property
    def open_meteo_azimuth(self) -> float:
        """Open-Meteo/PVGIS use 0=south, -90=east, 90=west, 180=north."""

        value = (self.azimuth_deg - 180.0) % 360.0
        return value - 360.0 if value > 180.0 else value

    def as_dict(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "kwp": self.kwp,
            "inverter_ac_mw": self.inverter_ac_mw,
            "tilt_deg": self.tilt_deg,
            "azimuth_deg": self.azimuth_deg,
            "tracking": self.tracking,
            "asset_scale": self.asset_scale,
            "performance_ratio": self.performance_ratio,
            "albedo": self.albedo,
        }

    def to_mw(self, poa_w_m2: pd.Series) -> pd.Series:
        """Convert plane-of-array irradiance (W/m2) to clipped MW."""

        clean = poa_w_m2.clip(lower=0.0).interpolate(limit_direction="both").fillna(0.0)
        power = self.scaled_kwp * (clean / 1000.0) * self.performance_ratio / 1000.0
        return power.clip(lower=0.0, upper=self.scaled_inverter_ac_mw)


def _check_timestamps(timestamps: pd.DatetimeIndex) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(timestamps)
    if index.tz is None:
        raise ValueError("timestamps must be timezone-aware (UTC)")
    index = index.tz_convert("UTC")
    if index.has_duplicates:
        raise ValueError("timestamps contain duplicates")
    return index.sort_values()


def _to_quarter_hour(hourly: pd.Series, timestamps: pd.DatetimeIndex) -> pd.Series:
    """Linearly interpolate an hourly UTC series onto the requested instants."""

    series = hourly.astype(float)
    series = series[~series.index.duplicated(keep="first")].sort_index()
    union = series.index.union(timestamps)
    filled = series.reindex(union).interpolate(method="time", limit_direction="both")
    return filled.reindex(timestamps).fillna(0.0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_path(cache_dir: Path, prefix: str, payload: dict) -> Path:
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{prefix}_{key}.json"


def _fetch_json(url: str, *, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read()[:300].decode("utf-8", "replace")
        except Exception:  # pragma: no cover - best effort
            pass
        raise PVFetchError(f"HTTP {exc.code} for {url}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PVFetchError(f"could not fetch {url}: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise PVFetchError(f"invalid JSON from {url}") from exc


def _write_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _solar_geometry(
    timestamps: pd.DatetimeIndex, latitude: float, longitude: float
) -> pd.DataFrame:
    """Return sin(elevation) and cos(zenith) for each timestamp (UTC)."""

    rows = []
    for ts in timestamps:
        day_of_year = ts.day_of_year
        declination = math.radians(23.45) * math.sin(
            2.0 * math.pi * (284 + day_of_year) / 365.0
        )
        solar_hour = ts.hour + ts.minute / 60.0 + longitude / 15.0
        hour_angle = math.radians(15.0 * (solar_hour - 12.0))
        lat = math.radians(latitude)
        sin_elevation = math.sin(lat) * math.sin(declination) + math.cos(
            lat
        ) * math.cos(declination) * math.cos(hour_angle)
        sin_elevation = max(-1.0, min(1.0, sin_elevation))
        rows.append((sin_elevation, max(0.0, sin_elevation)))
    return pd.DataFrame(rows, index=timestamps, columns=["sin_elevation", "cos_zenith"])


class MeteredPVSource:
    """PV from a metered CSV (already in MW or kW)."""

    name = "metered"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def series(self, timestamps: pd.DatetimeIndex) -> pd.Series:
        index = _check_timestamps(timestamps)
        frame = pd.read_csv(self.path)
        time_column = next(
            (column for column in ("timestamp_utc", "time", "timestamp") if column in frame),
            None,
        )
        if time_column is None:
            raise ValueError(f"{self.path}: expected timestamp_utc/time/timestamp column")
        if "pv_mw" in frame:
            values = pd.to_numeric(frame["pv_mw"], errors="coerce")
        elif "pv_kw" in frame:
            values = pd.to_numeric(frame["pv_kw"], errors="coerce") / 1000.0
        else:
            raise ValueError(f"{self.path}: expected pv_mw or pv_kw column")
        series = pd.Series(
            values.to_numpy(dtype=float),
            index=pd.to_datetime(frame[time_column], utc=True),
        )
        series = series[~series.index.duplicated(keep="first")].sort_index()
        result = _to_quarter_hour(series, index)
        return result.clip(lower=0.0)

    def metadata(self) -> dict:
        return {"source": self.name, "path": str(self.path), "sha256": _sha256(self.path)}


class OpenMeteoPVSource:
    """PV from Open-Meteo archived irradiance for the target period."""

    name = "open-meteo-archive"

    def __init__(
        self,
        spec: PVSpec,
        cache_dir: str | Path,
        *,
        timeout: float = 90.0,
    ):
        self.spec = spec
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self._raw: dict | None = None

    def _request_payload(self, start: date, end: date) -> dict:
        fixed = self.spec.tracking != "dual_axis"
        payload = {
            "latitude": self.spec.latitude,
            "longitude": self.spec.longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "timezone": "UTC",
        }
        if fixed:
            payload["hourly"] = "global_tilted_irradiance"
            payload["tilt"] = self.spec.tilt_deg
            payload["azimuth"] = self.spec.open_meteo_azimuth
        else:
            payload["hourly"] = (
                "direct_normal_irradiance,diffuse_radiation,shortwave_radiation"
            )
        return payload

    def _fetch(self, start: date, end: date) -> dict:
        payload = self._request_payload(start, end)
        cache = _cache_path(self.cache_dir, "open_meteo", payload)
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        query = "&".join(f"{key}={value}" for key, value in payload.items())
        data = _fetch_json(f"{OPEN_METEO_URL}?{query}", timeout=self.timeout)
        _write_cache(cache, data)
        return data

    def _hourly_frame(self, start: date, end: date) -> pd.DataFrame:
        data = self._fetch(start, end)
        hourly = data.get("hourly")
        if not isinstance(hourly, dict) or "time" not in hourly:
            raise PVFetchError("Open-Meteo response has no hourly block")
        index = pd.to_datetime(hourly["time"], utc=True, format="ISO8601")
        frame = pd.DataFrame(index=index)
        for column in ("global_tilted_irradiance", "direct_normal_irradiance",
                       "diffuse_radiation", "shortwave_radiation"):
            if column in hourly:
                frame[column] = pd.to_numeric(hourly[column], errors="coerce")
        return frame

    def _poa_hourly(self, frame: pd.DataFrame) -> pd.Series:
        if "global_tilted_irradiance" in frame:
            return frame["global_tilted_irradiance"]
        direct = frame["direct_normal_irradiance"].fillna(0.0)
        diffuse = frame["diffuse_radiation"].fillna(0.0)
        global_horizontal = frame["shortwave_radiation"].fillna(0.0)
        geometry = _solar_geometry(
            pd.DatetimeIndex(frame.index), self.spec.latitude, self.spec.longitude
        )
        cos_zenith = geometry["cos_zenith"].to_numpy()
        poa = (
            direct.to_numpy()
            + diffuse.to_numpy() * (1.0 + cos_zenith) / 2.0
            + self.spec.albedo * global_horizontal.to_numpy() * (1.0 - cos_zenith) / 2.0
        )
        return pd.Series(poa, index=frame.index)

    def series(self, timestamps: pd.DatetimeIndex) -> pd.Series:
        index = _check_timestamps(timestamps)
        start = index.min().date() - timedelta(days=1)
        end = index.max().date()
        frame = self._hourly_frame(start, end)
        poa = self._poa_hourly(frame)
        poa = poa.clip(lower=0.0).interpolate(limit_direction="both").fillna(0.0)
        quarter_hour = _to_quarter_hour(poa, index)
        return self.spec.to_mw(quarter_hour)

    def metadata(self) -> dict:
        return {
            "source": self.name,
            "spec": self.spec.as_dict(),
            "url": OPEN_METEO_URL,
            "cache_dir": str(self.cache_dir),
        }


class PVGISPVSource:
    """PV from PVGIS ``seriescalc`` (directly, or as a year proxy)."""

    def __init__(
        self,
        spec: PVSpec,
        cache_dir: str | Path,
        *,
        proxy_year: int = PVGIS_MAX_YEAR,
        timeout: float = 90.0,
    ):
        self.spec = spec
        self.cache_dir = Path(cache_dir)
        self.proxy_year = proxy_year
        self.timeout = timeout
        self.requested_year: int | None = None
        self.name = "pvgis"

    def _payload(self, year: int) -> dict:
        payload = {
            "lat": self.spec.latitude,
            "lon": self.spec.longitude,
            "startyear": year,
            "endyear": year,
            "pvcalculation": 1,
            "peakpower": self.spec.kwp,
            "pvtechchoice": "crystSi",
            "mountingplace": "free",
            "loss": 14,
            "outputformat": "json",
        }
        if self.spec.tracking == "dual_axis":
            payload["trackingtype"] = 3
        else:
            payload.update(
                {
                    "fixed": 1,
                    "angle": self.spec.tilt_deg,
                    "aspect": self.spec.open_meteo_azimuth,
                }
            )
        return payload

    def _fetch(self, year: int) -> dict:
        payload = self._payload(year)
        cache = _cache_path(self.cache_dir, "pvgis", payload)
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        query = "&".join(f"{key}={value}" for key, value in payload.items())
        data = _fetch_json(f"{PVGIS_URL}?{query}", timeout=self.timeout)
        _write_cache(cache, data)
        return data

    def _hourly(self, year: int) -> pd.Series:
        data = self._fetch(year)
        hourly = data.get("outputs", {}).get("hourly")
        if not isinstance(hourly, list) or not hourly:
            raise PVFetchError(f"PVGIS response for {year} has no hourly output")
        index = []
        values = []
        for row in hourly:
            # PVGIS labels each hour at :10; treat that as the start of the hour.
            stamp = datetime.strptime(row["time"], "%Y%m%d:%H%M").replace(tzinfo=UTC)
            index.append(stamp - timedelta(minutes=10))
            values.append(float(row["P"]))
        series = pd.Series(values, index=pd.DatetimeIndex(index)).sort_index()
        return series[~series.index.duplicated(keep="first")]

    def _project(self, series: pd.Series, timestamps: pd.DatetimeIndex) -> pd.Series:
        lookup = {
            (stamp.month, stamp.day, stamp.hour, stamp.minute): float(value)
            for stamp, value in series.items()
        }
        projected = []
        for stamp in timestamps:
            key = (stamp.month, stamp.day, stamp.hour, stamp.minute)
            if key not in lookup and stamp.month == 2 and stamp.day == 29:
                key = (2, 28, stamp.hour, stamp.minute)
            projected.append(lookup.get(key, float("nan")))
        return pd.Series(projected, index=timestamps)

    def series(self, timestamps: pd.DatetimeIndex) -> pd.Series:
        index = _check_timestamps(timestamps)
        target_year = int(index.min().year)
        direct = PVGIS_MIN_YEAR <= target_year <= PVGIS_MAX_YEAR
        year = target_year if direct else self.proxy_year
        if not PVGIS_MIN_YEAR <= year <= PVGIS_MAX_YEAR:
            raise ValueError(f"PVGIS year must be {PVGIS_MIN_YEAR}..{PVGIS_MAX_YEAR}")
        self.requested_year = year
        self.name = "pvgis" if direct else f"pvgis-{year}-proxy"
        hourly = self._hourly(year)
        if direct:
            source = hourly
        else:
            source = self._project(hourly, index)
        # PVGIS P is in W for the requested peak power; scale and convert to MW.
        power_mw = source * self.spec.asset_scale / 1_000_000.0
        quarter_hour = _to_quarter_hour(power_mw, index)
        return quarter_hour.clip(lower=0.0, upper=self.spec.scaled_inverter_ac_mw)

    def metadata(self) -> dict:
        return {
            "source": self.name,
            "spec": self.spec.as_dict(),
            "requested_year": self.requested_year,
            "proxy_year": None if self.name == "pvgis" else self.proxy_year,
            "url": PVGIS_URL,
            "cache_dir": str(self.cache_dir),
        }


class ClearSkyPVSource:
    """Deterministic clear-sky fallback used when no real source is available."""

    name = "clear-sky"

    def __init__(self, spec: PVSpec):
        self.spec = spec

    def series(self, timestamps: pd.DatetimeIndex) -> pd.Series:
        index = _check_timestamps(timestamps)
        geometry = _solar_geometry(index, self.spec.latitude, self.spec.longitude)
        sin_elevation = geometry["sin_elevation"].clip(lower=0.0)
        # Simple clear-sky global horizontal irradiance, then the same fixed-plane
        # efficiency model.  This is a fallback, not a calibrated PV model.
        ghi = 1000.0 * sin_elevation.pow(1.15)
        return self.spec.to_mw(ghi)

    def metadata(self) -> dict:
        return {"source": self.name, "spec": self.spec.as_dict()}
