"""Deterministic stubs for the ML PV forecast.

``StubPVModel`` is the contract-safe placeholder used by the dataset builder
until A2's trained model exists.  It is a day-over-day persistence forecast:
the value for interval ``t`` is the actual PV from ``t - 24 h``.  That value
is available at every issue time, so the forecast is causal by construction.
"""

from __future__ import annotations

import pandas as pd


class StubPVModel:
    """Causal day-over-day persistence forecast (never uses future weather)."""

    name = "stub-persistence-dod-v1"
    version = "1"

    def forecast(self, pv_mw: pd.Series, timestamps: pd.DatetimeIndex) -> pd.Series:
        """Return a forecast for every requested UTC timestamp."""

        index = pd.DatetimeIndex(timestamps)
        if index.tz is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        index = index.tz_convert("UTC")
        if pv_mw.index.has_duplicates:
            raise ValueError("pv_mw index contains duplicates")
        lagged = pv_mw.reindex(index - pd.Timedelta(hours=24))
        result = pd.Series(lagged.to_numpy(dtype=float), index=index)
        return result.interpolate(limit_direction="both").fillna(0.0).clip(lower=0.0)
