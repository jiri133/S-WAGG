# PV Forecast Model: Architecture, Training, Evaluation

Status: 2026-11-07
See also `PLAN.md` §5.4, `TEAM_PLAN.md` lane A2, `artifacts/models/pv/model_card.md`,
and `artifacts/models/pv/metrics.json`.

The A2 model forecasts PV power at 15-minute resolution for the receding-horizon dispatch
stack. The stack re-plans at local 00/04/08/12/16/20 and executes the next 16 intervals.

## 1. Purpose

- Target: `pv_mw` from the aligned dataset, already scaled by the farm `asset_scale`.
- Output: `pv_forecast_mw`, clipped to `[0, inverter AC × asset_scale]`.
- Resolution: 15 minutes. 96 intervals on normal days; 92 or 100 on DST days.
- Scope: one model per farm. The artifact stores the farm checksum and will not load
  against a different `farm.yaml`.

## 2. Architecture

```
                         ┌─────────────────────────────────────────────┐
                         │  aligned_2026.csv (A1)                      │
                         │  actual pv_mw, delivery_date, interval,     │
                         │  pv_forecast_issue_utc                      │
                         └──────────────────┬──────────────────────────┘
                                            │
        ┌───────────────────────────────────┼───────────────────────────────────┐
        │                                   │                                   │
        ▼                                   ▼                                   ▼
  realized PV lags                 NWP forecast run                    solar geometry
  pv_lag_1, pv_lag_2               ECMWF IFS HRES                      clear_sky_ghi
  pv_roll_4                        (Open-Meteo Single Runs)             clear_sky_index
  (only up to issue)               selected per issue boundary
        │                                   │                                   │
        │                          ghi, dni, dhi, cloud_cover,                  │
        │                          temperature, humidity, wind,                 │
        │                          precipitation, snow                          │
        │                                   │                                   │
        └───────────────────────────────────┼───────────────────────────────────┘
                                            │
                         ┌──────────────────▼──────────────────┐
                         │  air-quality archive                │
                         │  aerosol_optical_depth              │
                         └──────────────────┬──────────────────┘
                                            │
                         ┌──────────────────▼──────────────────┐
                         │  feature matrix (21 columns)        │
                         │  time + NWP + clear-sky + lags +    │
                         │  lead_steps + aerosol               │
                         └──────────────────┬──────────────────┘
                                            │
                         ┌──────────────────▼──────────────────┐
                         │  HistGradientBoostingRegressor      │
                         │  400 trees, lr 0.05, 31 leaves      │
                         └──────────────────┬──────────────────┘
                                            │
                         ┌──────────────────▼──────────────────┐
                         │  pv_forecast_mw (MW), clipped to    │
                         │  the inverter AC rating             │
                         └─────────────────────────────────────┘
```

### 2.1 Causality

A forecast issued at `s` uses only information available at `s`.

1. Issue boundaries: local 00/04/08/12/16/20 Europe/Bucharest, converted to UTC.
2. NWP run: the latest ECMWF IFS HRES run (00/06/12/18 UTC) published after a 6-hour lag.

   ```
   run = floor_to_6h(issue_utc - 6h)
   ```

   If that run is missing, the client falls back to the previous available run (up to
   8 × 6 h) and caches the mapping.

   | Local issue | UTC (winter) | UTC (summer) | Latest published run |
   |---|---|---|---|
   | 00:00 | 22:00 | 21:00 | 12:00 |
   | 04:00 | 02:00 | 01:00 | 18:00 previous day |
   | 08:00 | 06:00 | 05:00 | 00:00 / 18:00 previous day |
   | 12:00 | 10:00 | 09:00 | 00:00 |
   | 16:00 | 14:00 | 13:00 | 06:00 |
   | 20:00 | 18:00 | 17:00 | 12:00 / 06:00 |

3. NWP values at the target come from that run's forecast horizon.
4. Realized PV lags (`pv_lag_1`, `pv_lag_2`, `pv_roll_4`) use actual PV at or before the
   issue.
5. The target `pv_mw` is never a feature.
6. `clear_sky_ghi` comes from solar geometry (latitude, longitude, date, time), not from
   observed weather.

One exception: aerosol is read from the historical air-quality archive at the target
time, not from an issue-time forecast. See §9.

### 2.2 Forecast views

The model produces two views.

- **Per-row.** Each interval uses the latest issue at or before it. Lead is 0–4 h 45 m.
  Written to `aligned_2026.csv` as `pv_forecast_mw`.
- **Rest-of-day snapshot.** One issue per decision boundary covers all remaining
  intervals. Used for lead-time metrics and the context builder. Written to
  `artifacts/models/pv/pv_forecast_snapshots.csv`.

## 3. Features

`configs/pv_model.yaml` defines the ordered feature list. All 21 features are numeric.

| Group | Features | Source | Why |
|---|---|---|---|
| Time | `hour_sin`, `hour_cos`, `doy_sin`, `doy_cos`, `month` | Delivery interval / date | Diurnal and seasonal PV shape |
| NWP irradiance | `ghi`, `dni`, `dhi` | Run available at the issue | Main physical driver |
| NWP weather | `cloud_cover`, `temperature`, `humidity`, `wind_speed`, `precipitation`, `snow` | Same run | Cloud, thermal and soiling effects |
| Clear-sky | `clear_sky_ghi`, `clear_sky_index` | Solar geometry + `ghi` | Separates clear-sky potential from weather attenuation |
| Lead | `lead_steps` | `target − issue` / 15 min | Learns lead-dependent bias |
| Realized PV | `pv_lag_1`, `pv_lag_2`, `pv_roll_4` | Actual PV at the issue | Current state and short-horizon persistence |
| Aerosol | `aerosol` | Air-quality archive | Aerosol attenuation (see §9) |

Feature engineering lives in `src/battery_rl/models/pv.py::PVForecastModel.build_features`.
Features are grouped by issue, and the hourly NWP frame is interpolated to the 15-minute
target grid.

Site geometry is not a feature. The model trains per farm and the target is already
scaled, so kWp, inverter AC, tilt, azimuth and tracking are constant. Pooling farms would
change that.

## 4. Model choice

`HistGradientBoostingRegressor` fits this problem.

- PV is nonlinear. Irradiance, cloud cover, solar angle and time of day interact. Trees
  capture those interactions without hand-written physics.
- Cloud cover and clear-sky index act like thresholds. Trees split on them.
- The model handles missing values. NWP gaps and absent variables are common.
- Features use different units (W/m², °C, m/s, degrees, dimensionless). Trees do not need
  scaling or imputation.
- It ships with scikit-learn, so no LightGBM or XGBoost install is needed. Training takes
  tens of seconds on a laptop CPU.
- About 20k rows do not justify an LSTM or Transformer. A linear model cannot represent
  the interactions. A random forest is slower and larger. A physical model is already used
  for the actual-PV proxy (archived irradiance × PR) and would need site calibration to
  become a forecast.

Hyperparameters were fixed before evaluation.

| Parameter | Value |
|---|---|
| Loss | squared error |
| Learning rate | 0.05 |
| Iterations | 400 |
| Max leaves | 31 |
| Min samples per leaf | 20 |
| L2 regularization | 1.0 |
| Early stopping | off |
| Random seed | 42 |

The test split was not used for tuning. Validation was used for reporting, not model
selection.

## 5. Training

### 5.1 Data and splits

Training uses `artifacts/data/processed/aligned_2026.csv`: 29,760 intervals over 310
delivery days (2026-01-01 → 2026-11-06).

| Split | Dates | Rows | Use |
|---|---|---|---|
| Train | 2026-01-01 → 2026-07-31 | 20,348 | Fitting |
| Validation | 2026-08-01 → 2026-09-30 | 5,856 | Reporting and sanity check |
| Test | 2026-10-01 → 2026-11-06 | 3,556 | Final held-out evaluation |

The split is chronological and frozen in `configs/eval.yaml` and `splits.json`. The test
split is never used for fitting or model selection.

### 5.2 Steps

1. Load the aligned dataset and build a realized-PV series indexed by UTC.
2. For every issue boundary, select the required NWP run and prefetch it. Runs are cached
   under `artifacts/data/raw/nwp/`.
3. Build the 21-column feature matrix.
4. Fit on the train split only.
5. Predict train, validation and test rows for the per-row metrics.
6. Build rest-of-day snapshots for every validation/test day and every decision boundary.
7. Save the artifact, metrics, predictions, snapshots and model card.

### 5.3 Artifact

`artifacts/models/pv/pv_model.joblib` stores the estimator, feature order, PV config, farm
checksum and training metadata.

`PVForecastModel.load` rejects an artifact whose farm checksum or feature list does not
match `configs/farm.yaml` or `configs/pv_model.yaml`. Re-exporting the farm config forces
a retrain, which prevents applying a model to a different plant by accident.

### 5.4 Reproduce

```powershell
cd RL
.venv\Scripts\python.exe scripts/train_pv.py
.venv\Scripts\python.exe scripts/build_dataset.py --pv-forecast model
```

The first run downloads the NWP runs; later runs use the cache. Use `--start/--end` for a
subset, `--max-workers` for fetch concurrency, and `--quiet` for less logging.

## 6. How efficiency was measured

Efficiency here means forecast skill. Computational cost is in §8.

### 6.1 Metrics

For every finite actual \(y_i\) and forecast \(\hat{y}_i\):

- **MAE**, mean absolute error in MW:
  \[
  \mathrm{MAE} = \frac{1}{N}\sum_{i=1}^{N} |\hat{y}_i - y_i|
  \]
- **RMSE**, root mean squared error in MW. Penalizes large misses:
  \[
  \mathrm{RMSE} = \sqrt{\frac{1}{N}\sum_{i=1}^{N} (\hat{y}_i - y_i)^2}
  \]
- **Bias**, mean signed error in MW. Positive means over-forecast:
  \[
  \mathrm{Bias} = \frac{1}{N}\sum_{i=1}^{N} (\hat{y}_i - y_i)
  \]

MAE is the headline metric because dispatch cost is linear in energy: MW errors translate
into misscheduled energy. RMSE exposes large single-interval misses. Bias shows systematic
over- or under-forecasting.

### 6.2 Two evaluation views

1. **Per-row.** Each interval is scored against the forecast from its latest issue
   boundary (0–4 h lead). This is the step-level view in the aligned dataset.
2. **Rest-of-day snapshot.** Each decision boundary produces a forecast for every
   remaining interval of that day. Rows are binned by lead time (0–4, 4–8, …, 20–24 h).
   This is the view that matters for the agent's planning horizon.

The views are not directly comparable. The snapshot includes long leads, so its overall
MAE is higher.

### 6.3 Baseline

The causal baseline is day-over-day persistence:

\[
\hat{y}_t^{\text{persistence}} = y_{t-24h}
\]

It uses only realized PV from the previous day. It is a cheap reference and the ML model
is compared against it on the same rows and splits.

### 6.4 Slices

Results are reported overall and sliced by:

- lead time (snapshot view),
- month,
- season (winter: Dec–Feb, spring: Mar–May, summer: Jun–Aug, autumn: Sep–Nov).

Every slice reports `n`, so empty or small slices are visible.

## 7. Results

### 7.1 Overall, per-row, 0–4 h lead

| Split | n | MAE (MW) | RMSE (MW) | Bias (MW) | Persistence MAE (MW) | MAE improvement |
|---|---|---|---|---|---|---|
| Train | 20,348 | 0.0584 | 0.1089 | +0.0004 | 0.4953 | 88.2% |
| Validation | 5,856 | 0.1615 | 0.3425 | +0.0188 | 0.4253 | 62.0% |
| Test | 3,556 | 0.0971 | 0.2230 | +0.0358 | 0.3795 | 74.4% |

Train metrics are in-sample. Validation and test are out-of-sample. The model beats
persistence on both held-out splits: 62.0% lower MAE on validation and 74.4% lower on
test.

Test errors are lower than validation errors because October–November has less irradiance
and less absolute PV variability than August–September. Absolute MW errors shrink.
Relative skill is higher.

### 7.2 By lead time, rest-of-day snapshots

| Lead | Val MAE | Val RMSE | Val n | Test MAE | Test RMSE | Test n |
|---|---|---|---|---|---|---|
| 0–4 h | 0.1615 | 0.3425 | 5,856 | 0.0972 | 0.2231 | 3,552 |
| 4–8 h | 0.2220 | 0.4103 | 4,880 | 0.1387 | 0.2672 | 2,960 |
| 8–12 h | 0.3425 | 0.5280 | 3,904 | 0.1772 | 0.3129 | 2,368 |
| 12–16 h | 0.3785 | 0.5907 | 2,928 | 0.1748 | 0.3311 | 1,776 |
| 16–20 h | 0.3259 | 0.5492 | 1,952 | 0.1137 | 0.2580 | 1,184 |
| 20–24 h | 0.0539 | 0.1290 | 976 | 0.0147 | 0.0162 | 592 |
| 24–48 h | — | — | 0 | 0.0002 | 0.0003 | 4 |

Snapshot overall: validation MAE 0.2519 MW, RMSE 0.4540. Test MAE 0.1310 MW, RMSE 0.2681.

Error grows with lead through the middle of the day. The 20–24 h bucket is mostly night,
where PV is near zero. The 24–48 h bucket has 4 rows from the fall-back edge; ignore it.

### 7.3 By month

| Month | Split | MAE (MW) | n |
|---|---|---|---|
| Jan | train | 0.0364 | 2,976 |
| Feb | train | 0.0446 | 2,688 |
| Mar | train | 0.0441 | 2,972 |
| Apr | train | 0.0683 | 2,880 |
| May | train | 0.0763 | 2,976 |
| Jun | train | 0.0694 | 2,880 |
| Jul | train | 0.0687 | 2,976 |
| Aug | val | 0.1495 | 2,976 |
| Sep | val | 0.1739 | 2,880 |
| Oct | test | 0.1044 | 2,980 |
| Nov | test | 0.0592 | 576 |

### 7.4 By season

| Season | Split | MAE (MW) | n |
|---|---|---|---|
| Winter | train | 0.0403 | 5,664 |
| Spring | train | 0.0629 | 8,828 |
| Summer | train | 0.0690 | 5,856 |
| Summer | val | 0.1495 | 2,976 |
| Autumn | val | 0.1739 | 2,880 |
| Autumn | test | 0.0971 | 3,556 |

Validation summer and autumn errors are larger in absolute MW than test autumn errors
because August–September PV is larger and more variable. nMAE would narrow the gap; it is
not in the current metrics.

### 7.5 Checks

- Forecasts are non-negative and never exceed the scaled inverter AC rating.
- Actual and forecast PV correlate at 0.994 on the full dataset, including in-sample train
  rows. Treat this as a sanity check, not a skill metric.
- Issue times are always at or before the target. Lag range: 0–285 minutes. The maximum is
  on the fall-back day, where the first 4-hour block spans 5 physical hours.
- Missing actuals are counted, not filled. The dataset has 0 missing PV actuals and 5
  incomplete intervals on the load side.

## 8. Computational cost

Measured on the development laptop with the NWP cache warm.

| Step | Approximate cost |
|---|---|
| NWP fetch, first full run (1,241 runs, 4 workers) | 2–3 minutes |
| Feature build, 29,760 rows | ~20 seconds |
| Fit, 20,348 × 21 | ~20 seconds |
| Rest-of-day snapshots, 32,932 rows | ~1–2 minutes |
| Artifact size | 1.5 MB |
| Inference | one vectorized `predict`, no GPU |

The dominant cost is network I/O on the first run and feature construction. Both are
cached and reproducible offline afterwards.

## 9. Limitations

1. **PV actual is a proxy.** `pv_mw` comes from Open-Meteo archived irradiance and farm
   geometry (PR 0.85), not metered generation. The model inherits that bias. A metered
   15-minute series should replace it: set `metered_pv_path` in `farm.yaml`, rebuild, and
   retrain.
2. **Aerosol is not issue-time causal.** It is read from the historical archive at the
   target time. Aerosol changes slowly and its effect is small, but the strict version
   should use the last value at or before the issue, or a CAMS forecast.
3. **One model per farm.** Site geometry is constant in training. Pooling farms needs
   geometry features and a grouped split.
4. **Hyperparameters are fixed.** The config schema reserves LightGBM and XGBoost, but the
   current trainer implements HistGradientBoosting only. A validation-only search could
   help; the test split must stay untouched.
5. **No uncertainty.** The model predicts the mean. Quantile forecasts or ensembles would
   support risk-aware scheduling.
6. **No economic metric.** Evaluation reports MW error, not the RON impact on dispatch.
   That belongs to lane B and should weight errors by price and marginal battery value.
7. **Per-row vs snapshot.** `aligned_2026.csv` holds a 0–4 h forecast. For rest-of-day
   planning use `pv_forecast_snapshots.csv`.
8. **Archive gaps.** Missing NWP runs fall back to older runs, so the effective lead can
   exceed the nominal 6-hour lag. The mapping is cached but not exposed per row.

## 10. File map

| Path | Role |
|---|---|
| `src/battery_rl/data/nwp.py` | Single Runs client, run selection/fallback, cache, aerosol |
| `src/battery_rl/models/pv.py` | Feature builder, HGB model, save/load, metrics |
| `scripts/train_pv.py` | Training, snapshots, metrics, model card |
| `scripts/build_dataset.py` | Dataset rebuild with `--pv-forecast model` |
| `tests/test_pv_model.py` | Causality, run mapping, cache/fallback, fit/save/load |
| `configs/pv_model.yaml` | Model, NWP source/model/lag, feature list |
| `artifacts/models/pv/pv_model.joblib` | Trained artifact |
| `artifacts/models/pv/metrics.json` | Full metrics including snapshots |
| `artifacts/models/pv/model_card.md` | Short generated model card |
| `artifacts/models/pv/predictions.csv` | Per-row predictions |
| `artifacts/models/pv/pv_forecast_snapshots.csv` | Rest-of-day forecasts per issue |
| `artifacts/data/processed/aligned_2026.csv` | Dataset with `pv_forecast_mw` |
| `artifacts/data/processed/dataset_meta.json` | Model and NWP provenance, checksums |
