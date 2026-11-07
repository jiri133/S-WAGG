# PV forecast model card

Model: `hgb-pv-v1` v1
Trained: `2026-11-07T19:32:06.129043+00:00`
Dataset: `C:\Users\danai\OneDrive\Documents\Smarthack\S-WAGG\RL\artifacts\data\processed\aligned_2026.csv` (29760 rows)
NWP: `open-meteo-single-runs` / `ecmwf_ifs`, run lag 6.0 h

## Overall metrics

| Split | MAE (MW) | RMSE (MW) | Bias (MW) | n |
|---|---|---|---|---|
| train | 0.0584 | 0.1089 | +0.0004 | 20348 |
| val | 0.1615 | 0.3425 | +0.0188 | 5856 |
| test | 0.0971 | 0.2230 | +0.0358 | 3556 |

## Validation and test by lead time (rest-of-day snapshots)

### val

| Lead | MAE (MW) | RMSE (MW) | n |
|---|---|---|---|
| 0-4h | 0.1615 | 0.3425 | 5856 |
| 4-8h | 0.2220 | 0.4103 | 4880 |
| 8-12h | 0.3425 | 0.5280 | 3904 |
| 12-16h | 0.3785 | 0.5907 | 2928 |
| 16-20h | 0.3259 | 0.5492 | 1952 |
| 20-24h | 0.0539 | 0.1290 | 976 |

### test

| Lead | MAE (MW) | RMSE (MW) | n |
|---|---|---|---|
| 0-4h | 0.0972 | 0.2231 | 3552 |
| 4-8h | 0.1387 | 0.2672 | 2960 |
| 8-12h | 0.1772 | 0.3129 | 2368 |
| 12-16h | 0.1748 | 0.3311 | 1776 |
| 16-20h | 0.1137 | 0.2580 | 1184 |
| 20-24h | 0.0147 | 0.0162 | 592 |
| 24-48h | 0.0002 | 0.0003 | 4 |

## Baselines (overall)

| Split | ML MAE | Persistence MAE |
|---|---|---|
| val | 0.1615 | 0.4253 |
| test | 0.0971 | 0.3795 |

## Notes

- Forecasts use the Open-Meteo Single Runs API; each issue uses the latest ECMWF IFS run available after the configured publication lag.
- `pv_lag_*` features use realized PV at or before the issue only.
- Training is chronological; the test split is never used for fitting.
- The aligned dataset's `pv_forecast_mw` uses each row's latest issue (0-4 h lead). The rest-of-day snapshots used for the lead-time table are written to `pv_forecast_snapshots.csv`.
