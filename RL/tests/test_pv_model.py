"""Tests for the A2 PV forecast model and its causal NWP features.

No network is required: the Single Runs client is exercised with a
monkeypatched ``_fetch_json`` and the model uses a fake NWP source.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from battery_rl.config import load_farm_config, load_pv_model_config
from battery_rl.data import nwp as nwp_module
from battery_rl.data.dataset import build_aligned
from battery_rl.data.nwp import (
    NWP_FEATURES,
    NWPFetchError,
    SingleRunNWP,
    latest_run,
)
from battery_rl.data.opcom import STEP, expected_intervals, local_midnight_utc
from battery_rl.models.pv import (
    PVForecastModel,
    metrics_by_lead,
    metrics_by_month,
    metrics_by_season,
    regression_metrics,
)
from battery_rl.models.stub import StubPVModel

ROOT = Path(__file__).resolve().parents[1]


class FakeNWP:
    """Deterministic NWP source for feature tests."""

    def __init__(self, value: float = 100.0):
        self.value = value
        self.prefetched: list = []

    def prefetch(self, issues) -> None:
        self.prefetched.extend(list(issues))

    def frame_for_issue(self, issue, timestamps) -> pd.DataFrame:
        index = pd.DatetimeIndex(timestamps)
        return pd.DataFrame(
            {name: np.full(len(index), self.value) for name in NWP_FEATURES},
            index=index,
        )


def _day_frame(day: date) -> tuple[pd.DataFrame, pd.Series]:
    intervals = expected_intervals(day)
    start = local_midnight_utc(day)
    stamps = [start + STEP * index for index in range(intervals)]
    prices = pd.DataFrame(
        {
            "timestamp_utc": stamps,
            "delivery_date": [day] * intervals,
            "interval": list(range(1, intervals + 1)),
            "price_ron_mwh": np.linspace(400.0, 900.0, intervals),
        }
    )
    load = pd.DataFrame(
        {
            "timestamp_utc": stamps,
            "load_mw": np.full(intervals, 5000.0),
            "load_forecast_mw": np.full(intervals, 5020.0),
        }
    )
    pv_index = pd.date_range(
        start - timedelta(days=2), start + timedelta(days=1), freq="15min"
    )
    hours = pv_index.hour + pv_index.minute / 60.0
    pv = pd.Series(4.0 * np.maximum(0.0, np.sin((hours - 6.0) / 12.0 * np.pi)), index=pv_index)
    frame = build_aligned(prices, load, pv, StubPVModel(), start=day, end=day)
    return frame, pv


def test_latest_run_mapping() -> None:
    assert latest_run(datetime(2026, 1, 15, 14, 0, tzinfo=UTC)) == datetime(
        2026, 1, 15, 6, 0, tzinfo=UTC
    )
    assert latest_run(datetime(2026, 1, 15, 2, 0, tzinfo=UTC)) == datetime(
        2026, 1, 14, 18, 0, tzinfo=UTC
    )
    assert latest_run(datetime(2026, 7, 1, 1, 0, tzinfo=UTC)) == datetime(
        2026, 6, 30, 18, 0, tzinfo=UTC
    )
    with pytest.raises(NWPFetchError, match="precedes"):
        latest_run(datetime(2024, 1, 1, tzinfo=UTC))


def test_single_run_nwp_parses_and_caches(tmp_path: Path, monkeypatch) -> None:
    hours = pd.date_range("2026-01-15T06:00", "2026-01-15T18:00", freq="h", tz="UTC")
    payload = {
        "hourly": {
            "time": [stamp.strftime("%Y-%m-%dT%H:%M") for stamp in hours],
            **{
                api_name: list(np.linspace(0.0, 500.0, len(hours)))
                for api_name in nwp_module.NWP_VARIABLES
            },
        }
    }
    monkeypatch.setattr(nwp_module, "_fetch_json", lambda url, timeout: payload)
    source = SingleRunNWP(46.77, 25.93, tmp_path, run_lag_hours=6.0)
    issue = datetime(2026, 1, 15, 14, 0, tzinfo=UTC)
    timestamps = pd.date_range(
        "2026-01-15T14:00", "2026-01-15T15:00", freq="15min", tz="UTC"
    )
    frame = source.frame_for_issue(issue, timestamps)
    assert list(frame.columns) == NWP_FEATURES
    assert (frame["ghi"] >= 0.0).all()
    assert (tmp_path / "ecmwf_ifs_20260115T0600.json").exists()


def test_nwp_falls_back_to_previous_run(tmp_path: Path, monkeypatch) -> None:
    hours = pd.date_range("2026-01-15T06:00", "2026-01-15T18:00", freq="h", tz="UTC")
    payload = {
        "hourly": {
            "time": [stamp.strftime("%Y-%m-%dT%H:%M") for stamp in hours],
            **{
                api_name: list(np.linspace(0.0, 500.0, len(hours)))
                for api_name in nwp_module.NWP_VARIABLES
            },
        }
    }
    calls: list[str] = []

    def fake_fetch(url: str, timeout: float) -> dict:
        calls.append(url)
        if "run=2026-01-15T06%3A00" in url:
            raise NWPFetchError(
                'HTTP 400: {"reason":"The requested model run is not available"}'
            )
        return payload

    monkeypatch.setattr(nwp_module, "_fetch_json", fake_fetch)
    source = SingleRunNWP(46.77, 25.93, tmp_path, max_run_fallbacks=2)
    frame = source.frame_for_run(datetime(2026, 1, 15, 6, 0, tzinfo=UTC))
    assert not frame.empty
    assert any("run=2026-01-15T00%3A00" in url for url in calls)
    assert (tmp_path / "ecmwf_ifs_20260115T0600.json").exists()


def test_feature_builder_is_causal() -> None:
    frame, pv = _day_frame(date(2026, 1, 15))
    model = PVForecastModel(load_pv_model_config(), load_farm_config(), FakeNWP())
    features = model.build_features(frame, pv)
    assert list(features.columns) == load_pv_model_config().features

    cutoff = pd.Timestamp("2026-01-15T12:00:00Z")
    modified = pv.copy()
    modified[modified.index > cutoff] = 100.0
    changed = model.build_features(frame, modified)
    before = frame["timestamp_utc"] <= cutoff
    pd.testing.assert_frame_equal(features[before], changed[before])

    # Realized PV lags must never look past the issue boundary.
    assert (features["lead_steps"] >= 0.0).all()
    assert (features["pv_lag_1"] >= 0.0).all()


def test_fit_predict_save_load(tmp_path: Path) -> None:
    frame, pv = _day_frame(date(2026, 1, 15))
    config = load_pv_model_config()
    farm = load_farm_config()
    model = PVForecastModel(config, farm, FakeNWP())
    features = model.build_features(frame, pv)
    target = frame["pv_mw"]
    model.fit(features, target)
    prediction = model.predict(features)
    assert np.isfinite(prediction).all()
    assert (prediction >= 0.0).all()
    assert (prediction <= farm.scaled_inverter_ac_mw).all()

    path = model.save(tmp_path / "model.joblib")
    loaded = PVForecastModel.load(
        path, config=config, farm=farm, nwp=FakeNWP(), aerosol=None
    )
    np.testing.assert_allclose(loaded.predict(features), prediction, rtol=1e-9)


def test_feature_builder_rejects_unknown_feature() -> None:
    frame, pv = _day_frame(date(2026, 1, 15))
    config = load_pv_model_config().model_copy(update={"features": ["not_a_feature"]})
    model = PVForecastModel(config, load_farm_config(), FakeNWP())
    with pytest.raises(ValueError, match="unbuildable"):
        model.build_features(frame, pv)


def test_build_aligned_accepts_forecast_frame() -> None:
    frame, pv = _day_frame(date(2026, 1, 15))

    class OneModel:
        def forecast_frame(self, work, pv_series):
            return pd.Series(np.ones(len(work)), index=work.index)

    prices = frame[["timestamp_utc", "delivery_date", "interval", "price_ron_mwh"]]
    load = frame[["timestamp_utc", "load_mw", "load_forecast_mw"]]
    rebuilt = build_aligned(
        prices, load, pv, OneModel(), start=date(2026, 1, 15), end=date(2026, 1, 15)
    )
    assert (rebuilt["pv_forecast_mw"] == 1.0).all()


def test_regression_metrics() -> None:
    truth = np.array([0.0, 1.0, 2.0, np.nan])
    prediction = np.array([0.0, 2.0, 2.0, 5.0])
    result = regression_metrics(truth, prediction)
    assert result["n"] == 3
    assert result["mae"] == pytest.approx(1.0 / 3.0)
    assert result["rmse"] == pytest.approx(np.sqrt(1.0 / 3.0))
    assert result["bias"] == pytest.approx(1.0 / 3.0)


def test_metrics_slices() -> None:
    truth = np.array([1.0, 1.0, 1.0, 1.0])
    prediction = np.array([2.0, 2.0, 2.0, 2.0])
    by_lead = metrics_by_lead(truth, prediction, np.array([0.5, 3.0, 5.0, 30.0]))
    assert by_lead["0-4h"]["n"] == 2
    assert by_lead["4-8h"]["n"] == 1
    assert by_lead["24-48h"]["n"] == 1
    assert (
        metrics_by_lead(np.array([1.0]), np.array([2.0]), np.array([0.5]))["0-4h"]["mae"]
        == 1.0
    )

    months = np.array([1, 4, 7, 10])
    by_month = metrics_by_month(truth, prediction, months)
    assert set(by_month) == {"01", "04", "07", "10"}
    by_season = metrics_by_season(truth, prediction, months)
    assert set(by_season) == {"winter", "spring", "summer", "autumn"}
