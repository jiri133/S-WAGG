# Aligned 2026 dataset data card

Generated: `2026-11-07T19:45:19.586579+00:00`

## Scope

- Delivery dates: **2026-01-01 .. 2026-11-06**
- Rows: **29760**, days: **310**
- DST days kept at their real lengths: `{'2026-03-29': 92, '2026-10-25': 100}`
- Incomplete intervals: **5**

## Sources

- Prices: `C:\Users\danai\OneDrive\Documents\Smarthack\S-WAGG\RL\artifacts\data\processed\opcom_pzu_2026.csv` (sha256 `52d1974757c982ce...`)
- Load: `C:\Users\danai\OneDrive\Documents\Smarthack\S-WAGG\RL\artifacts\data\processed\ENTSO_15MIN.csv` (sha256 `0254b3cbb626c257...`)
- PV: **open-meteo-archive**
- PV model: 6000 kWp x 1 asset scale, inverter 6.00 MW x 1, PR 0.85, tracking `dual_axis`

## Known caveats

- `pv_mw` is derived from archived irradiance and the farm geometry; it is a proxy for metered generation, not a measurement. Prefer a metered CSV when one exists.
- PVGIS only serves years 2005-2023. Selecting `--pv-source pvgis` for 2026 uses the latest available year as a day-of-year proxy; the metadata records it.
- `pv_forecast_mw` is produced by the trained model `hgb-pv-v1` v1; artifact `C:\Users\danai\OneDrive\Documents\Smarthack\S-WAGG\RL\artifacts\models\pv\pv_model.joblib`. See the model card and metrics under `artifacts/models/pv/`.
- Rest-of-day forecasts for validation/test evaluation are snapshotted in `artifacts/models/pv/pv_forecast_snapshots.csv`.
- ENTSO-E labels are CET/CEST, while OPCOM delivery days are Europe/Bucharest; the join is by UTC. The first OPCOM hour of 2026-01-01 precedes the ENTSO-E series and is marked incomplete.

## Missing values

| Column | Missing intervals |
|---|---|
| `price_ron_mwh` | 0 |
| `load_mw` | 5 |
| `load_forecast_mw` | 4 |
| `pv_mw` | 0 |
| `pv_forecast_mw` | 0 |
| `pv_forecast_issue_utc` | 0 |

## Columns

| Column | Unit |
|---|---|
| `timestamp_utc` | ISO 8601 UTC |
| `delivery_date` | Europe/Bucharest local date |
| `interval` | 1..N (N = 92, 96 or 100) |
| `price_ron_mwh` | RON/MWh |
| `load_mw` | MW |
| `load_forecast_mw` | MW |
| `pv_mw` | MW (scaled by farm asset_scale) |
| `pv_forecast_mw` | MW (scaled by farm asset_scale) |
| `pv_forecast_issue_utc` | ISO 8601 UTC |
| `is_complete` | bool |

## Reproduce

```powershell
.venv\Scripts\python.exe scripts/build_dataset.py --pv-source auto --pv-forecast model
```
