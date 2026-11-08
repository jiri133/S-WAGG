"""ML PV forecast model (Phase 1B, lane A2).

Builds one feature row per 15-minute interval from:

- the NWP run that was available at the interval's 4-hour issue boundary,
- time encodings, clear-sky irradiance and clear-sky index,
- realized PV lags at the issue time (never future actuals),
- aerosol optical depth.

The estimator is a ``HistGradientBoostingRegressor``; the artifact stores the
fitted model, the feature order and the farm-config checksum.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from ..config import FarmConfig, PVModelConfig
from ..data.nwp import NWP_FEATURES, SingleRunNWP
from ..data.pv import clear_sky_ghi

LEAD_BINS_HOURS = (0.0, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0, 48.0)


class PVForecastModel:
    """Feature builder + HistGradientBoosting PV model."""

    name = "hgb-pv-v1"
    version = "1"

    def __init__(
        self,
        config: PVModelConfig,
        farm: FarmConfig,
        nwp: SingleRunNWP,
        aerosol: pd.Series | None = None,
    ):
        self.config = config
        self.farm = farm
        self.nwp = nwp
        self.aerosol = aerosol
        self.estimator: HistGradientBoostingRegressor | None = None
        self.feature_names_: list[str] = list(config.features)

    # ------------------------------------------------------------------
    # Features
    # ------------------------------------------------------------------

    def build_features(self, frame: pd.DataFrame, pv_series: pd.Series) -> pd.DataFrame:
        """Build the configured feature matrix, aligned with ``frame`` rows."""

        required = {"timestamp_utc", "delivery_date", "interval", "pv_forecast_issue_utc"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"feature frame is missing columns: {sorted(missing)}")
        if pv_series.index.has_duplicates:
            raise ValueError("pv_series index contains duplicates")

        work = frame.copy()
        work["timestamp_utc"] = pd.to_datetime(work["timestamp_utc"], utc=True)
        work["pv_forecast_issue_utc"] = pd.to_datetime(
            work["pv_forecast_issue_utc"], utc=True
        )
        work["delivery_date"] = pd.to_datetime(work["delivery_date"]).dt.date
        work["interval"] = work["interval"].astype(int)
        self.nwp.prefetch(work["pv_forecast_issue_utc"].unique())

        features = pd.DataFrame(index=work.index)
        for column in NWP_FEATURES:
            features[column] = np.nan
        for issue, group in work.groupby("pv_forecast_issue_utc", sort=False):
            stamps = pd.DatetimeIndex(group["timestamp_utc"])
            nwp = self.nwp.frame_for_issue(issue, stamps)
            features.loc[group.index, NWP_FEATURES] = nwp[NWP_FEATURES].to_numpy(
                dtype=float
            )

        local_hour = (work["interval"].to_numpy(dtype=float) - 1.0) * 0.25
        features["hour_sin"] = np.sin(2.0 * np.pi * local_hour / 24.0)
        features["hour_cos"] = np.cos(2.0 * np.pi * local_hour / 24.0)

        dates = pd.to_datetime(work["delivery_date"])
        day_of_year = dates.dt.day_of_year.to_numpy(dtype=float)
        features["doy_sin"] = np.sin(2.0 * np.pi * day_of_year / 365.25)
        features["doy_cos"] = np.cos(2.0 * np.pi * day_of_year / 365.25)
        features["month"] = dates.dt.month.to_numpy(dtype=float)

        clear = clear_sky_ghi(
            pd.DatetimeIndex(work["timestamp_utc"]),
            self.farm.latitude,
            self.farm.longitude,
        ).to_numpy(dtype=float)
        features["clear_sky_ghi"] = clear
        ghi = pd.to_numeric(features["ghi"], errors="coerce").to_numpy(dtype=float)
        features["clear_sky_index"] = np.where(
            clear > 1.0,
            np.clip(ghi / np.maximum(clear, 1.0), 0.0, 3.0),
            0.0,
        )

        issue = pd.DatetimeIndex(work["pv_forecast_issue_utc"])
        features["lead_steps"] = (
            (work["timestamp_utc"] - work["pv_forecast_issue_utc"]).dt.total_seconds()
            / 900.0
        ).to_numpy(dtype=float)

        pv = pd.to_numeric(pv_series.astype(float), errors="coerce").sort_index()
        pv = pv[~pv.index.duplicated(keep="first")]
        features["pv_lag_1"] = pv.reindex(issue - pd.Timedelta(minutes=15)).to_numpy(
            dtype=float
        )
        features["pv_lag_2"] = pv.reindex(issue - pd.Timedelta(minutes=30)).to_numpy(
            dtype=float
        )
        rolling = np.vstack(
            [
                pv.reindex(issue - pd.Timedelta(minutes=15 * step)).to_numpy(dtype=float)
                for step in range(4)
            ]
        )
        counts = np.isfinite(rolling).sum(axis=0)
        features["pv_roll_4"] = np.where(
            counts > 0, np.nansum(rolling, axis=0) / np.maximum(counts, 1), 0.0
        )
        features[["pv_lag_1", "pv_lag_2", "pv_roll_4"]] = (
            features[["pv_lag_1", "pv_lag_2", "pv_roll_4"]]
            .fillna(0.0)
            .clip(lower=0.0)
        )

        if self.aerosol is not None and not self.aerosol.empty:
            aerosol = self.aerosol.reindex(work["timestamp_utc"])
            aerosol = aerosol.interpolate(method="time", limit_direction="both")
            features["aerosol"] = aerosol.to_numpy(dtype=float)
        else:
            features["aerosol"] = 0.0
        features["aerosol"] = features["aerosol"].fillna(0.0)

        missing_features = [name for name in self.config.features if name not in features]
        if missing_features:
            raise ValueError(f"unbuildable features: {missing_features}")
        return features[self.config.features].astype(float)

    # ------------------------------------------------------------------
    # Fit / predict
    # ------------------------------------------------------------------

    def fit(self, features: pd.DataFrame, target: pd.Series | np.ndarray) -> PVForecastModel:
        values = np.asarray(target, dtype=float)
        mask = np.isfinite(values)
        if not mask.any():
            raise ValueError("target has no finite values")
        matrix = features[self.config.features].to_numpy(dtype=float)
        self.estimator = HistGradientBoostingRegressor(
            loss="squared_error",
            learning_rate=0.05,
            max_iter=400,
            max_leaf_nodes=31,
            min_samples_leaf=20,
            l2_regularization=1.0,
            early_stopping=False,
            random_state=self.config.random_seed,
        )
        self.estimator.fit(matrix[mask], values[mask])
        self.feature_names_ = list(self.config.features)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if self.estimator is None:
            raise RuntimeError("model is not fitted")
        matrix = features[self.feature_names_].to_numpy(dtype=float)
        raw = self.estimator.predict(matrix)
        upper = self.farm.scaled_inverter_ac_mw
        return np.clip(raw, 0.0, upper)

    def forecast_frame(self, frame: pd.DataFrame, pv_series: pd.Series) -> pd.Series:
        """Forecast aligned with ``frame`` rows (used by the dataset builder)."""

        features = self.build_features(frame, pv_series)
        prediction = self.predict(features)
        return pd.Series(prediction, index=frame.index, name="pv_forecast_mw")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path, *, extra: dict | None = None) -> Path:
        if self.estimator is None:
            raise RuntimeError("cannot save an unfitted model")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": self.name,
            "version": self.version,
            "model": self.estimator,
            "features": self.feature_names_,
            "config": self.config.model_dump(mode="json"),
            "farm_checksum": self.farm.checksum(),
            "farm": {
                "name": self.farm.name,
                "latitude": self.farm.latitude,
                "longitude": self.farm.longitude,
                "asset_scale": self.farm.asset_scale,
            },
            "extra": extra or {},
        }
        tmp = target.with_suffix(target.suffix + ".part")
        joblib.dump(payload, tmp)
        tmp.replace(target)
        return target

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        config: PVModelConfig,
        farm: FarmConfig,
        nwp: SingleRunNWP,
        aerosol: pd.Series | None = None,
    ) -> PVForecastModel:
        payload = joblib.load(path)
        if payload.get("farm_checksum") != farm.checksum():
            raise ValueError(
                "PV model artifact was trained for a different farm config; retrain it"
            )
        features = list(payload.get("features", []))
        if features != list(config.features):
            raise ValueError(
                "PV model feature list differs from configs/pv_model.yaml; retrain it"
            )
        model = cls(config, farm, nwp, aerosol)
        model.estimator = payload["model"]
        model.feature_names_ = features
        return model

    def metadata(self, *, artifact: str | Path | None = None) -> dict:
        return {
            "model": self.name,
            "version": self.version,
            "status": "trained",
            "features": self.feature_names_,
            "nwp": self.nwp.metadata(),
            "farm_checksum": self.farm.checksum(),
            "artifact": None if artifact is None else str(artifact),
        }


# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------


def regression_metrics(
    y_true: np.ndarray | pd.Series, y_pred: np.ndarray | pd.Series
) -> dict:
    """MAE, RMSE and bias over finite pairs."""

    truth = np.asarray(y_true, dtype=float)
    prediction = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(truth) & np.isfinite(prediction)
    if not mask.any():
        return {"n": 0, "mae": None, "rmse": None, "bias": None}
    residual = prediction[mask] - truth[mask]
    return {
        "n": int(mask.sum()),
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "bias": float(np.mean(residual)),
    }


def metrics_by_lead(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
    lead_hours: np.ndarray | pd.Series,
    bins: tuple[float, ...] = LEAD_BINS_HOURS,
) -> dict[str, dict]:
    """MAE/RMSE/n by lead-time bucket."""

    truth = np.asarray(y_true, dtype=float)
    prediction = np.asarray(y_pred, dtype=float)
    lead = np.asarray(lead_hours, dtype=float)
    result: dict[str, dict] = {}
    for lower, upper in zip(bins, bins[1:], strict=False):
        mask = (lead >= lower) & (lead < upper)
        label = f"{lower:g}-{upper:g}h"
        result[label] = regression_metrics(truth[mask], prediction[mask])
    return result


def metrics_by_month(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
    months: np.ndarray | pd.Series,
) -> dict[str, dict]:
    truth = np.asarray(y_true, dtype=float)
    prediction = np.asarray(y_pred, dtype=float)
    values = np.asarray(months, dtype=int)
    return {
        f"{month:02d}": regression_metrics(truth[values == month], prediction[values == month])
        for month in range(1, 13)
        if (values == month).any()
    }


def metrics_by_season(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
    months: np.ndarray | pd.Series,
) -> dict[str, dict]:
    truth = np.asarray(y_true, dtype=float)
    prediction = np.asarray(y_pred, dtype=float)
    values = np.asarray(months, dtype=int)
    seasons = {
        "winter": (12, 1, 2),
        "spring": (3, 4, 5),
        "summer": (6, 7, 8),
        "autumn": (9, 10, 11),
    }
    return {
        name: regression_metrics(
            truth[np.isin(values, members)], prediction[np.isin(values, members)]
        )
        for name, members in seasons.items()
    }
