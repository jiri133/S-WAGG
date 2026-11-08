"""Contract tests for the aligned 15-minute dataset (A1).

No network is required: the PV source tests either use the deterministic
clear-sky model, a local metered CSV, or a monkeypatched Open-Meteo response.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from battery_rl.config import load_eval_config
from battery_rl.data.dataset import (
    ALIGNED_COLUMNS,
    DatasetContractError,
    build_aligned,
    load_days,
    load_split,
    validate_aligned,
    write_aligned_csv,
    write_splits,
)
from battery_rl.data.entsoe import (
    EntsoParseError,
    parse_entsoe_csv,
    parse_mtu_label,
)
from battery_rl.data.forecasts import (
    attach_issue_times,
    decision_boundaries_utc,
)
from battery_rl.data.opcom import STEP, expected_intervals, local_midnight_utc
from battery_rl.data.pv import (
    ClearSkyPVSource,
    MeteredPVSource,
    OpenMeteoPVSource,
    PVSpec,
)
from battery_rl.models.stub import StubPVModel

ROOT = Path(__file__).resolve().parents[1]
PRICE_CSV = ROOT / "artifacts/data/processed/opcom_pzu_2026.csv"
LOAD_CSV = ROOT / "artifacts/data/processed/ENTSO_15MIN.csv"


def _spec(**overrides) -> PVSpec:
    values = {
        "latitude": 46.7744,
        "longitude": 25.9308,
        "kwp": 6000.0,
        "inverter_ac_mw": 6.0,
        "tilt_deg": 30.0,
        "azimuth_deg": 180.0,
        "tracking": "none",
        "asset_scale": 1.0,
        "performance_ratio": 0.85,
    }
    values.update(overrides)
    return PVSpec(**values)


def _prices(day: date) -> pd.DataFrame:
    intervals = expected_intervals(day)
    start = local_midnight_utc(day)
    timestamps = [start + STEP * index for index in range(intervals)]
    return pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "delivery_date": [day] * intervals,
            "interval": list(range(1, intervals + 1)),
            "price_ron_mwh": np.linspace(400.0, 900.0, intervals),
        }
    )


def _load(frame: pd.DataFrame, gap_index: int | None = None) -> pd.DataFrame:
    values = np.full(len(frame), 5000.0)
    forecast = values + 20.0
    if gap_index is not None:
        values[gap_index] = np.nan
        forecast[gap_index] = np.nan
    return pd.DataFrame(
        {
            "timestamp_utc": frame["timestamp_utc"],
            "load_mw": values,
            "load_forecast_mw": forecast,
        }
    )


def _pv(frame: pd.DataFrame, days_before: int = 2) -> pd.Series:
    index = pd.date_range(
        frame["timestamp_utc"].min() - timedelta(days=days_before),
        frame["timestamp_utc"].max(),
        freq="15min",
    )
    hours = index.hour + index.minute / 60.0
    values = np.maximum(0.0, np.sin((hours - 6.0) / 12.0 * np.pi)) * 4.0
    return pd.Series(values, index=index, name="pv_mw")


def _build_day(day: date, *, gap_index: int | None = None) -> pd.DataFrame:
    prices = _prices(day)
    return build_aligned(
        prices,
        _load(prices, gap_index=gap_index),
        _pv(prices),
        StubPVModel(),
        start=day,
        end=day,
    )


# ---------------------------------------------------------------------------
# ENTSO-E parsing and time zones
# ---------------------------------------------------------------------------


def test_parse_mtu_label_offsets() -> None:
    assert parse_mtu_label("01/01/2026 00:00") == datetime(2025, 12, 31, 23, 0, tzinfo=UTC)
    assert parse_mtu_label("01/07/2026 00:00") == datetime(2026, 6, 30, 22, 0, tzinfo=UTC)
    assert parse_mtu_label("29/03/2026 03:00 (CEST)") == datetime(
        2026, 3, 29, 1, 0, tzinfo=UTC
    )
    assert parse_mtu_label("25/10/2026 02:30 (CEST)") == datetime(
        2026, 10, 25, 0, 30, tzinfo=UTC
    )
    assert parse_mtu_label("25/10/2026 02:30 (CET)") == datetime(
        2026, 10, 25, 1, 30, tzinfo=UTC
    )


def test_parse_entsoe_csv_area_and_gaps(tmp_path: Path) -> None:
    path = tmp_path / "entsoe.csv"
    path.write_text(
        ", ".join(
            [
                '"MTU (CET/CEST)"',
                '"Area"',
                '"Actual Total Load (MW)"',
                '"Day-ahead Total Load Forecast (MW)"',
            ]
        )
        + "\n"
        '"01/01/2026 00:00 - 01/01/2026 00:15", "BZN|RO", "5788.00", "5790.00"\n'
        '"01/01/2026 00:15 - 01/01/2026 00:30", "BZN|RO", "-", "5740.00"\n'
        '"01/01/2026 00:30 - 01/01/2026 00:45", "BZN|RO", "5670.00", "-"\n'
        '"01/01/2026 00:45 - 01/01/2026 01:00", "BZN|DE", "9999.00", "9999.00"\n',
        encoding="utf-8",
    )
    rows = parse_entsoe_csv(path, validate=False)
    assert len(rows) == 3  # the BZN|DE row is filtered out
    assert rows[0].timestamp_utc == datetime(2025, 12, 31, 23, 0, tzinfo=UTC)
    assert rows[0].is_complete
    assert rows[1].load_mw is None
    assert rows[1].load_forecast_mw == 5740.0
    assert not rows[1].is_complete
    assert rows[2].load_forecast_mw is None


def test_parse_entsoe_continuity_validation(tmp_path: Path) -> None:
    path = tmp_path / "gap.csv"
    path.write_text(
        '"01/01/2026 00:00 - 01/01/2026 00:15", "BZN|RO", "1.0", "1.0"\n'
        '"01/01/2026 00:30 - 01/01/2026 00:45", "BZN|RO", "1.0", "1.0"\n',
        encoding="utf-8",
    )
    with pytest.raises(EntsoParseError, match="irregular step"):
        parse_entsoe_csv(path)


@pytest.mark.skipif(not LOAD_CSV.exists(), reason="processed ENTSO CSV not available")
def test_real_entsoe_file_is_a_full_year() -> None:
    from battery_rl.data.entsoe import parse_entsoe_csv

    rows = parse_entsoe_csv(LOAD_CSV)
    assert len(rows) == 35040
    assert rows[0].timestamp_utc == datetime(2025, 12, 31, 23, 0, tzinfo=UTC)
    assert rows[-1].timestamp_utc == datetime(2026, 12, 31, 22, 45, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Forecast issue boundaries
# ---------------------------------------------------------------------------


def test_decision_boundaries_follow_local_dst() -> None:
    normal = decision_boundaries_utc(date(2026, 1, 1))
    assert normal[0] == datetime(2025, 12, 31, 22, 0, tzinfo=UTC)
    assert normal[-1] == datetime(2026, 1, 1, 18, 0, tzinfo=UTC)

    spring = decision_boundaries_utc(date(2026, 3, 29))
    assert spring[1] - spring[0] == timedelta(hours=3)
    assert spring[-1] - spring[-2] == timedelta(hours=4)

    autumn = decision_boundaries_utc(date(2026, 10, 25))
    assert autumn[1] - autumn[0] == timedelta(hours=5)
    assert autumn[-1] - autumn[-2] == timedelta(hours=4)


def test_attach_issue_times_is_causal() -> None:
    frame = _prices(date(2026, 1, 15))
    result = attach_issue_times(frame)
    assert (result["pv_forecast_issue_utc"] <= result["timestamp_utc"]).all()
    assert result["pv_forecast_issue_utc"].iloc[0] == datetime(
        2026, 1, 14, 22, 0, tzinfo=UTC
    )
    assert result["pv_forecast_issue_utc"].iloc[-1] == datetime(
        2026, 1, 15, 18, 0, tzinfo=UTC
    )


# ---------------------------------------------------------------------------
# Aligned dataset contract
# ---------------------------------------------------------------------------


def test_build_aligned_normal_day() -> None:
    frame = _build_day(date(2026, 1, 15), gap_index=10)
    assert list(frame.columns) == ALIGNED_COLUMNS
    report = validate_aligned(frame)
    assert report["rows"] == 96
    assert report["days"] == 1
    assert report["incomplete_rows"] == 1
    assert report["missing"]["load_mw"] == 1
    assert not frame.loc[10, "is_complete"]
    assert frame.loc[0, "is_complete"]
    assert (frame["pv_forecast_issue_utc"] <= frame["timestamp_utc"]).all()


@pytest.mark.parametrize("day, intervals", [(date(2026, 3, 29), 92), (date(2026, 10, 25), 100)])
def test_dst_day_round_trip(tmp_path: Path, day: date, intervals: int) -> None:
    frame = _build_day(day)
    report = validate_aligned(frame)
    assert report["rows"] == intervals
    assert report["dst_days"] == {day.isoformat(): intervals}

    path = tmp_path / "aligned.csv"
    write_aligned_csv(frame, path)
    days = load_days(path)
    assert list(days) == [day]
    assert days[day].intervals == intervals
    assert len(days[day].price_ron_mwh) == intervals
    assert days[day].is_complete.dtype == bool
    assert days[day].pv_forecast_issue_utc[0].endswith("+00:00")


def test_load_split(tmp_path: Path) -> None:
    days = [date(2026, 1, 15), date(2026, 1, 16)]
    frames = [_build_day(day) for day in days]
    path = tmp_path / "aligned.csv"
    write_aligned_csv(pd.concat(frames, ignore_index=True), path)
    splits_path = tmp_path / "splits.json"
    splits_path.write_text(
        json.dumps(
            {
                "train": ["2026-01-15", "2026-01-16"],
                "val": ["2026-01-17", "2026-01-18"],
                "test": ["2026-01-19", "2026-01-20"],
            }
        ),
        encoding="utf-8",
    )
    train = load_split("train", dataset_path=path, splits_path=splits_path)
    assert [item.day for item in train] == days
    assert load_split("val", dataset_path=path, splits_path=splits_path) == []


def test_write_splits(tmp_path: Path) -> None:
    config = load_eval_config(ROOT / "configs/eval.yaml")
    path = write_splits(config, tmp_path / "splits.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["train"] == ["2026-01-01", "2026-07-31"]
    assert payload["val"] == ["2026-08-01", "2026-09-30"]
    assert payload["test"] == ["2026-10-01", "2026-11-06"]


def test_validate_rejects_future_forecast_issue() -> None:
    frame = _build_day(date(2026, 1, 15))
    broken = frame.copy()
    broken.loc[0, "pv_forecast_issue_utc"] = broken.loc[0, "timestamp_utc"] + pd.Timedelta(
        minutes=15
    )
    with pytest.raises(DatasetContractError, match="after its target"):
        validate_aligned(broken)


def test_validate_rejects_wrong_interval_count() -> None:
    frame = _build_day(date(2026, 1, 15))
    with pytest.raises(DatasetContractError, match="intervals"):
        validate_aligned(frame.iloc[:-1].copy())


def test_validate_rejects_negative_pv() -> None:
    frame = _build_day(date(2026, 1, 15))
    broken = frame.copy()
    broken.loc[0, "pv_mw"] = -0.1
    with pytest.raises(DatasetContractError, match="negative"):
        validate_aligned(broken)


def test_validate_rejects_inconsistent_completeness() -> None:
    frame = _build_day(date(2026, 1, 15))
    broken = frame.copy()
    broken.loc[0, "is_complete"] = False
    with pytest.raises(DatasetContractError, match="is_complete"):
        validate_aligned(broken)


@pytest.mark.parametrize(
    "name, intervals",
    [
        ("tiny_day.csv", 96),
        ("tiny_day_spring.csv", 92),
        ("tiny_day_fall.csv", 100),
    ],
)
def test_tiny_day_fixtures_load(name: str, intervals: int) -> None:
    path = ROOT / "tests/fixtures" / name
    days = load_days(path)
    assert len(days) == 1
    day = next(iter(days))
    assert days[day].intervals == intervals
    assert bool(days[day].is_complete.all())


@pytest.mark.skipif(
    not (PRICE_CSV.exists() and LOAD_CSV.exists()),
    reason="processed price/load CSVs not available",
)
def test_real_inputs_one_day() -> None:
    from battery_rl.data.entsoe import load_entsoe_frame

    day = date(2026, 1, 15)
    prices = pd.read_csv(PRICE_CSV)
    prices["delivery_date"] = pd.to_datetime(prices["delivery_date"]).dt.date
    prices = prices[prices["delivery_date"] == day].copy()
    load = load_entsoe_frame(LOAD_CSV)
    pv_index = pd.date_range(
        local_midnight_utc(day) - timedelta(days=2),
        local_midnight_utc(day) + timedelta(days=1),
        freq="15min",
    )
    pv = ClearSkyPVSource(_spec()).series(pv_index)
    frame = build_aligned(prices, load, pv, StubPVModel(), start=day, end=day)
    report = validate_aligned(frame)
    assert report["rows"] == 96
    assert report["incomplete_rows"] == 0


# ---------------------------------------------------------------------------
# PV sources
# ---------------------------------------------------------------------------


def test_spec_azimuth_convention() -> None:
    assert _spec(azimuth_deg=180.0).open_meteo_azimuth == 0.0
    assert _spec(azimuth_deg=90.0).open_meteo_azimuth == -90.0
    assert _spec(azimuth_deg=270.0).open_meteo_azimuth == 90.0
    assert _spec(azimuth_deg=0.0).open_meteo_azimuth == 180.0


def test_pv_is_clipped_to_inverter() -> None:
    spec = _spec(inverter_ac_mw=2.0)
    index = pd.date_range("2026-01-01", periods=4, freq="15min", tz="UTC")
    series = spec.to_mw(pd.Series([0.0, 500.0, 2000.0, 5000.0], index=index))
    assert (series >= 0.0).all()
    assert (series <= 2.0).all()
    assert series.iloc[3] == 2.0


def test_clear_sky_source_has_a_daytime_peak() -> None:
    index = pd.date_range("2026-06-21", "2026-06-22", freq="15min", tz="UTC", inclusive="left")
    series = ClearSkyPVSource(_spec()).series(index)
    assert (series >= 0.0).all()
    assert series.max() > 1.0
    assert series.iloc[0] == 0.0
    assert series.max() <= 6.0


def test_metered_source_interpolates_and_converts_kw(tmp_path: Path) -> None:
    path = tmp_path / "metered.csv"
    path.write_text(
        "timestamp_utc,pv_kw\n"
        "2026-01-01T00:00:00Z,0\n"
        "2026-01-01T00:30:00Z,1000\n",
        encoding="utf-8",
    )
    index = pd.date_range("2026-01-01T00:00:00Z", periods=3, freq="15min")
    series = MeteredPVSource(path).series(index)
    assert series.iloc[0] == 0.0
    assert series.iloc[1] == pytest.approx(0.5)
    assert series.iloc[2] == pytest.approx(1.0)


def test_open_meteo_source_parses_and_scales(tmp_path: Path, monkeypatch) -> None:
    from battery_rl.data import pv as pv_module

    hourly = {
        "hourly": {
            "time": ["2026-06-21T10:00", "2026-06-21T11:00", "2026-06-21T12:00"],
            "global_tilted_irradiance": [0.0, 900.0, 0.0],
        }
    }
    monkeypatch.setattr(pv_module, "_fetch_json", lambda url, timeout: hourly)
    index = pd.date_range("2026-06-21T10:00:00Z", "2026-06-21T12:00:00Z", freq="15min")
    series = OpenMeteoPVSource(_spec(), tmp_path).series(index)
    assert series.max() == pytest.approx(6000.0 * 0.9 * 0.85 / 1000.0)
    assert (series >= 0.0).all()
    assert list(tmp_path.glob("open_meteo_*.json"))


def test_open_meteo_dual_axis_uses_poa_model(tmp_path: Path, monkeypatch) -> None:
    from battery_rl.data import pv as pv_module

    hourly = {
        "hourly": {
            "time": ["2026-06-21T10:00", "2026-06-21T11:00", "2026-06-21T12:00"],
            "direct_normal_irradiance": [0.0, 700.0, 0.0],
            "diffuse_radiation": [0.0, 150.0, 0.0],
            "shortwave_radiation": [0.0, 800.0, 0.0],
        }
    }
    monkeypatch.setattr(pv_module, "_fetch_json", lambda url, timeout: hourly)
    index = pd.date_range("2026-06-21T10:00:00Z", "2026-06-21T12:00:00Z", freq="15min")
    series = OpenMeteoPVSource(_spec(tracking="dual_axis"), tmp_path).series(index)
    assert series.max() > 0.0
    assert series.max() <= 6.0
