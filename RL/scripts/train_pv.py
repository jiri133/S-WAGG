#!/usr/bin/env python3
"""Train the ML PV forecast model (Phase 1B, lane A2).

The script trains on the chronological train split, reports MAE/RMSE on the
validation and test splits (overall, by lead time, by month and by season),
and writes a model artifact plus metrics and predictions.  It never uses
future actual weather: every feature comes from the NWP run available at the
interval's 4-hour issue boundary or from realized PV at or before that issue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battery_rl.config import (  # noqa: E402
    load_eval_config,
    load_farm_config,
    load_pv_model_config,
)
from battery_rl.data.forecasts import decision_boundaries_utc  # noqa: E402
from battery_rl.data.nwp import NWPFetchError, SingleRunNWP, fetch_aerosol  # noqa: E402
from battery_rl.models.pv import (  # noqa: E402
    PVForecastModel,
    metrics_by_lead,
    metrics_by_month,
    metrics_by_season,
    regression_metrics,
)

LOGGER = logging.getLogger("battery_rl.train_pv")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "artifacts/data/processed/aligned_2026.csv"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    frame["pv_forecast_issue_utc"] = pd.to_datetime(
        frame["pv_forecast_issue_utc"], utc=True
    )
    frame["delivery_date"] = pd.to_datetime(frame["delivery_date"]).dt.date
    frame["interval"] = frame["interval"].astype(int)
    return frame


def _split_masks(frame: pd.DataFrame, eval_config) -> dict[str, pd.Series]:
    delivery = pd.to_datetime(frame["delivery_date"]).dt.date
    split = eval_config.split
    return {
        "train": (delivery >= eval_config.date_range.start) & (delivery <= split.train_end),
        "val": (delivery > split.train_end) & (delivery <= split.val_end),
        "test": (delivery > split.val_end) & (delivery <= split.test_end),
    }


def _build_snapshots(
    model: PVForecastModel,
    frame: pd.DataFrame,
    pv_series: pd.Series,
    masks: dict[str, pd.Series],
) -> pd.DataFrame:
    """Rest-of-day forecast from every decision boundary on val/test days."""

    rows: list[pd.DataFrame] = []
    for day, day_rows in frame.groupby("delivery_date", sort=True):
        if masks["val"].loc[day_rows.index].any():
            split = "val"
        elif masks["test"].loc[day_rows.index].any():
            split = "test"
        else:
            continue
        for issue in decision_boundaries_utc(day):
            subset = day_rows[day_rows["timestamp_utc"] >= issue].copy()
            if subset.empty:
                continue
            subset["pv_forecast_issue_utc"] = issue
            features = model.build_features(subset, pv_series)
            prediction = model.predict(features)
            rows.append(
                pd.DataFrame(
                    {
                        "issue_utc": issue,
                        "timestamp_utc": subset["timestamp_utc"].to_numpy(),
                        "delivery_date": day,
                        "interval": subset["interval"].to_numpy(),
                        "lead_hours": (
                            subset["timestamp_utc"] - issue
                        ).dt.total_seconds().to_numpy()
                        / 3600.0,
                        "pv_mw": subset["pv_mw"].to_numpy(dtype=float),
                        "pv_forecast_mw": prediction,
                        "split": split,
                    }
                )
            )
    if not rows:
        return pd.DataFrame(
            columns=[
                "issue_utc",
                "timestamp_utc",
                "delivery_date",
                "interval",
                "lead_hours",
                "pv_mw",
                "pv_forecast_mw",
                "split",
            ]
        )
    return pd.concat(rows, ignore_index=True)


def _model_card(payload: dict) -> str:
    lines = [
        "# PV forecast model card",
        "",
        f"Model: `{payload['model']}` v{payload['version']}",
        f"Trained: `{payload['trained_at_utc']}`",
        f"Dataset: `{payload['dataset']}` ({payload['rows']} rows)",
        f"NWP: `{payload['nwp']['source']}` / `{payload['nwp']['model']}`, "
        f"run lag {payload['nwp']['run_lag_hours']} h",
        "",
        "## Overall metrics",
        "",
        "| Split | MAE (MW) | RMSE (MW) | Bias (MW) | n |",
        "|---|---|---|---|---|",
    ]
    for split in ("train", "val", "test"):
        overall = payload["splits"].get(split, {}).get("overall")
        if overall:
            lines.append(
                f"| {split} | {overall['mae']:.4f} | {overall['rmse']:.4f} | "
                f"{overall['bias']:+.4f} | {overall['n']} |"
            )
    snapshot_metrics = payload.get("snapshot_metrics", {})
    lines.extend(
        [
            "",
            "## Validation and test by lead time (rest-of-day snapshots)",
            "",
        ]
    )
    for split in ("val", "test"):
        block = snapshot_metrics.get(split, {}).get("by_lead")
        if not block:
            block = payload["splits"].get(split, {}).get("by_lead")
        if not block:
            continue
        lines.append(f"### {split}")
        lines.append("")
        lines.append("| Lead | MAE (MW) | RMSE (MW) | n |")
        lines.append("|---|---|---|---|")
        for label, values in block.items():
            if values["n"]:
                lines.append(
                    f"| {label} | {values['mae']:.4f} | {values['rmse']:.4f} | {values['n']} |"
                )
        lines.append("")
    lines.extend(
        [
            "## Baselines (overall)",
            "",
            "| Split | ML MAE | Persistence MAE |",
            "|---|---|---|",
        ]
    )
    for split in ("val", "test"):
        block = payload["splits"].get(split, {})
        if not block:
            continue
        ml = block["overall"]["mae"]
        persistence = block["persistence"]["mae"]
        lines.append(f"| {split} | {ml:.4f} | {persistence:.4f} |")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Forecasts use the Open-Meteo Single Runs API; each issue uses the latest "
            "ECMWF IFS run available after the configured publication lag.",
            "- `pv_lag_*` features use realized PV at or before the issue only.",
            "- Training is chronological; the test split is never used for fitting.",
            "- The aligned dataset's `pv_forecast_mw` uses each row's latest issue "
            "(0-4 h lead). The rest-of-day snapshots used for the lead-time table are "
            "written to `pv_forecast_snapshots.csv`.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the ML PV forecast model.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/farm.yaml")
    parser.add_argument(
        "--pv-model-config", type=Path, default=ROOT / "configs/pv_model.yaml"
    )
    parser.add_argument("--eval-config", type=Path, default=ROOT / "configs/eval.yaml")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--cache-dir", type=Path, default=ROOT / "artifacts/data/raw/nwp"
    )
    parser.add_argument(
        "--out", type=Path, default=ROOT / "artifacts/models/pv/pv_model.joblib"
    )
    parser.add_argument(
        "--metrics", type=Path, default=ROOT / "artifacts/models/pv/metrics.json"
    )
    parser.add_argument(
        "--predictions", type=Path, default=ROOT / "artifacts/models/pv/predictions.csv"
    )
    parser.add_argument(
        "--snapshots",
        type=Path,
        default=ROOT / "artifacts/models/pv/pv_forecast_snapshots.csv",
    )
    parser.add_argument(
        "--model-card", type=Path, default=ROOT / "artifacts/models/pv/model_card.md"
    )
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    farm = load_farm_config(args.config)
    pv_config = load_pv_model_config(args.pv_model_config)
    eval_config = load_eval_config(args.eval_config)
    start = args.start or eval_config.date_range.start
    end = args.end or eval_config.split.test_end

    frame = _load_frame(args.dataset)
    delivery = pd.to_datetime(frame["delivery_date"]).dt.date
    frame = frame[(delivery >= start) & (delivery <= end)].reset_index(drop=True)
    if frame.empty:
        raise SystemExit("no dataset rows in the requested range")

    pv_series = frame.set_index("timestamp_utc")["pv_mw"].astype(float)
    nwp = SingleRunNWP(
        farm.latitude,
        farm.longitude,
        args.cache_dir,
        model=pv_config.nwp_model,
        run_lag_hours=pv_config.nwp_run_lag_hours,
        max_workers=args.max_workers,
    )
    nwp.prefetch(sorted(frame["pv_forecast_issue_utc"].unique()))
    try:
        aerosol = fetch_aerosol(farm.latitude, farm.longitude, start, end, args.cache_dir)
    except NWPFetchError as exc:
        LOGGER.warning("aerosol fetch failed (%s); using 0.0", exc)
        aerosol = None

    model = PVForecastModel(pv_config, farm, nwp, aerosol)
    LOGGER.info("building features for %d rows", len(frame))
    features = model.build_features(frame, pv_series)
    target = frame["pv_mw"].astype(float)
    masks = _split_masks(frame, eval_config)
    if not masks["train"].any():
        raise SystemExit("the train split is empty; check --start/--end and eval.yaml")

    LOGGER.info("fitting %s on %d training rows", model.name, int(masks["train"].sum()))
    model.fit(features[masks["train"]], target[masks["train"]])
    predictions = model.predict(features)

    result = frame[
        ["timestamp_utc", "delivery_date", "interval", "pv_mw", "pv_forecast_issue_utc"]
    ].copy()
    result["pv_forecast_mw"] = predictions
    result["lead_hours"] = (
        result["timestamp_utc"] - result["pv_forecast_issue_utc"]
    ).dt.total_seconds() / 3600.0
    result["split"] = np.select(
        [masks["train"].to_numpy(), masks["val"].to_numpy(), masks["test"].to_numpy()],
        ["train", "val", "test"],
        default="other",
    )

    months = pd.to_datetime(result["delivery_date"]).dt.month.to_numpy()
    metrics: dict[str, dict] = {}
    for split in ("train", "val", "test"):
        mask = masks[split]
        if not mask.any():
            continue
        truth = target[mask].to_numpy(dtype=float)
        pred = predictions[mask]
        split_result = {
            "overall": regression_metrics(truth, pred),
            "by_lead": metrics_by_lead(truth, pred, result.loc[mask, "lead_hours"].to_numpy()),
            "by_month": metrics_by_month(truth, pred, months[mask.to_numpy()]),
            "by_season": metrics_by_season(truth, pred, months[mask.to_numpy()]),
        }
        lagged = pv_series.reindex(
            pd.DatetimeIndex(result.loc[mask, "timestamp_utc"]) - pd.Timedelta(hours=24)
        )
        split_result["persistence"] = regression_metrics(
            truth, np.nan_to_num(lagged.to_numpy(dtype=float), nan=0.0)
        )
        metrics[split] = split_result

    LOGGER.info("building rest-of-day snapshots for val/test")
    snapshots = _build_snapshots(model, frame, pv_series, masks)
    snapshot_metrics: dict[str, dict] = {}
    for split in ("val", "test"):
        subset = snapshots[snapshots["split"] == split]
        if subset.empty:
            continue
        snapshot_metrics[split] = {
            "n_snapshots": int(len(subset)),
            "overall": regression_metrics(subset["pv_mw"], subset["pv_forecast_mw"]),
            "by_lead": metrics_by_lead(
                subset["pv_mw"], subset["pv_forecast_mw"], subset["lead_hours"]
            ),
            "by_month": metrics_by_month(
                subset["pv_mw"],
                subset["pv_forecast_mw"],
                pd.to_datetime(subset["delivery_date"]).dt.month.to_numpy(),
            ),
        }

    trained_at = datetime.now(UTC).isoformat()
    model.save(
        args.out,
        extra={
            "trained_at_utc": trained_at,
            "dataset": str(args.dataset),
            "metrics": metrics,
        },
    )
    payload = {
        "model": model.name,
        "version": model.version,
        "trained_at_utc": trained_at,
        "dataset": str(args.dataset),
        "rows": int(len(frame)),
        "features": pv_config.features,
        "farm": {
            "name": farm.name,
            "checksum": farm.checksum(),
            "asset_scale": farm.asset_scale,
        },
        "nwp": nwp.metadata(),
        "splits": metrics,
        "snapshot_metrics": snapshot_metrics,
        "snapshots": str(args.snapshots),
        "model_sha256": _sha256(args.out),
        "artifact": str(args.out),
    }
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.predictions, index=False, float_format="%.6f")
    args.snapshots.parent.mkdir(parents=True, exist_ok=True)
    snapshots.to_csv(args.snapshots, index=False, float_format="%.6f")
    args.model_card.parent.mkdir(parents=True, exist_ok=True)
    args.model_card.write_text(_model_card(payload), encoding="utf-8")

    summary = {
        split: payload["splits"][split]["overall"]
        for split in ("train", "val", "test")
        if split in payload["splits"]
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
