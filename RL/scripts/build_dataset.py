#!/usr/bin/env python3
"""Build the aligned 15-minute dataset (Phase 1B, lane A1).

Example::

    python scripts/build_dataset.py --pv-source auto

The script refuses to run without an exported farm config unless an explicit
``--config`` is supplied, as required by PLAN.md section 2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battery_rl.config import (  # noqa: E402
    load_eval_config,
    load_farm_config,
    load_pv_model_config,
)
from battery_rl.data.dataset import (  # noqa: E402
    ALIGNED_COLUMNS,
    DATASET_PATH,
    SPLITS_PATH,
    UNITS,
    build_aligned,
    validate_aligned,
    write_aligned_csv,
    write_splits,
)
from battery_rl.data.entsoe import load_entsoe_frame  # noqa: E402
from battery_rl.data.forecasts import DECISION_LOCAL_HOURS  # noqa: E402
from battery_rl.data.pv import (  # noqa: E402
    ClearSkyPVSource,
    MeteredPVSource,
    OpenMeteoPVSource,
    PVFetchError,
    PVGISPVSource,
    PVSpec,
)
from battery_rl.models.stub import StubPVModel  # noqa: E402

LOGGER = logging.getLogger("battery_rl.build_dataset")
ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "artifacts/data/processed"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _spec(farm, performance_ratio: float) -> PVSpec:
    return PVSpec(
        latitude=farm.latitude,
        longitude=farm.longitude,
        kwp=farm.pv.kwp,
        inverter_ac_mw=farm.pv.inverter_ac_mw,
        tilt_deg=farm.pv.tilt_deg,
        azimuth_deg=farm.pv.azimuth_deg,
        tracking=farm.pv.tracking.value,
        asset_scale=farm.asset_scale,
        performance_ratio=performance_ratio,
    )


def _make_source(args, farm, spec: PVSpec):
    kind = args.pv_source
    metered = _resolve(args.metered_pv) or _resolve(farm.metered_pv_path)
    if kind == "auto":
        kind = "metered" if metered and metered.exists() else "open-meteo"
    if kind == "metered":
        if metered is None:
            raise SystemExit("--pv-source metered requires --metered-pv or farm.metered_pv_path")
        if not metered.exists():
            raise SystemExit(f"metered PV file not found: {metered}")
        return MeteredPVSource(metered)
    if kind == "open-meteo":
        return OpenMeteoPVSource(spec, args.cache_dir)
    if kind == "pvgis":
        return PVGISPVSource(spec, args.cache_dir, proxy_year=args.pvgis_year)
    if kind == "clear-sky":
        return ClearSkyPVSource(spec)
    raise SystemExit(f"unknown PV source: {kind}")


def _pv_series(source, timestamps, spec: PVSpec, allow_fallback: bool):
    try:
        return source.series(timestamps), source
    except PVFetchError as exc:
        if not allow_fallback:
            raise
        LOGGER.warning("PV fetch failed (%s); falling back to clear-sky", exc)
        fallback = ClearSkyPVSource(spec)
        return fallback.series(timestamps), fallback


def build(args) -> dict:
    farm = load_farm_config(args.config)
    eval_config = load_eval_config(args.eval_config)
    pv_model_config = load_pv_model_config(args.pv_model_config)

    start = args.start or eval_config.date_range.start
    end = args.end or eval_config.split.test_end
    if end < start:
        raise SystemExit("--end must not be before --start")

    if not args.price_csv.exists():
        raise SystemExit(f"price CSV not found: {args.price_csv}")
    if not args.load_csv.exists():
        raise SystemExit(f"load CSV not found: {args.load_csv}")

    prices = pd.read_csv(args.price_csv)
    load = load_entsoe_frame(args.load_csv)
    spec = _spec(farm, args.performance_ratio)
    source = _make_source(args, farm, spec)

    price_work = prices.copy()
    price_work["delivery_date"] = pd.to_datetime(price_work["delivery_date"]).dt.date
    price_work = price_work[
        (price_work["delivery_date"] >= start) & (price_work["delivery_date"] <= end)
    ]
    if price_work.empty:
        raise SystemExit(f"no prices between {start} and {end}")
    timestamps = pd.DatetimeIndex(
        pd.to_datetime(price_work["timestamp_utc"], utc=True)
    ).sort_values()
    # The persistence stub needs two days of history for the first delivery day.
    pv_timestamps = pd.date_range(
        timestamps.min() - timedelta(days=2),
        timestamps.max(),
        freq="15min",
    )

    pv_series, used_source = _pv_series(source, pv_timestamps, spec, args.allow_fallback)
    frame = build_aligned(
        prices,
        load,
        pv_series,
        StubPVModel(),
        start=start,
        end=end,
    )
    report = validate_aligned(frame)

    write_aligned_csv(frame, args.output)
    write_splits(eval_config, args.splits)

    meta = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "rows": report["rows"],
        "days": report["days"],
        "columns": ALIGNED_COLUMNS,
        "units": UNITS,
        "farm": {
            "name": farm.name,
            "checksum": farm.checksum(),
            "asset_scale": farm.asset_scale,
        },
        "sources": {
            "prices": {"path": str(args.price_csv), "sha256": _sha256(args.price_csv)},
            "load": {"path": str(args.load_csv), "sha256": _sha256(args.load_csv)},
            "pv": used_source.metadata(),
        },
        "pv_forecast": {
            "model": StubPVModel.name,
            "version": StubPVModel.version,
            "status": "stub-pending-A2",
            "replan_steps": pv_model_config.replan_steps,
            "horizon_steps": pv_model_config.horizon_steps,
            "issue_local_hours": list(DECISION_LOCAL_HOURS),
        },
        "configs": {
            "farm": str(args.config),
            "eval": str(args.eval_config),
            "pv_model": str(args.pv_model_config),
        },
        "output": {"dataset": str(args.output), "sha256": _sha256(args.output)},
        "validation": report,
    }

    args.meta.parent.mkdir(parents=True, exist_ok=True)
    args.meta.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    args.validation.parent.mkdir(parents=True, exist_ok=True)
    args.validation.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.data_card.parent.mkdir(parents=True, exist_ok=True)
    args.data_card.write_text(_data_card(meta, args), encoding="utf-8")
    return meta


def _data_card(meta: dict, args) -> str:
    report = meta["validation"]
    missing = report["missing"]
    pv_source = meta["sources"]["pv"]
    lines = [
        "# Aligned 2026 dataset data card",
        "",
        f"Generated: `{meta['generated_at_utc']}`",
        "",
        "## Scope",
        "",
        f"- Delivery dates: **{report['first_delivery_date']} .. {report['last_delivery_date']}**",
        f"- Rows: **{report['rows']}**, days: **{report['days']}**",
        f"- DST days kept at their real lengths: `{report['dst_days']}`",
        f"- Incomplete intervals: **{report['incomplete_rows']}**",
        "",
        "## Sources",
        "",
        f"- Prices: `{meta['sources']['prices']['path']}` "
        f"(sha256 `{meta['sources']['prices']['sha256'][:16]}...`)",
        f"- Load: `{meta['sources']['load']['path']}` "
        f"(sha256 `{meta['sources']['load']['sha256'][:16]}...`)",
        f"- PV: **{pv_source['source']}**",
    ]
    if "spec" in pv_source:
        spec = pv_source["spec"]
        lines.append(
            "- PV model: "
            f"{spec['kwp']:.0f} kWp x {spec['asset_scale']:g} asset scale, "
            f"inverter {spec['inverter_ac_mw']:.2f} MW x {spec['asset_scale']:g}, "
            f"PR {spec['performance_ratio']:.2f}, tracking `{spec['tracking']}`"
        )
    lines.extend(
        [
            "",
            "## Known caveats",
            "",
            "- `pv_mw` is derived from archived irradiance and the farm geometry; it is a "
            "proxy for metered generation, not a measurement. Prefer a metered CSV when "
            "one exists.",
            "- PVGIS only serves years 2005-2023. Selecting `--pv-source pvgis` for 2026 "
            "uses the latest available year as a day-of-year proxy; the metadata records it.",
            "- `pv_forecast_mw` is the causal day-over-day persistence stub "
            f"`{meta['pv_forecast']['model']}`. It will be replaced by the A2 ML model; "
            "do not tune against it.",
            "- ENTSO-E labels are CET/CEST, while OPCOM delivery days are Europe/Bucharest; "
            "the join is by UTC. The first OPCOM hour of 2026-01-01 precedes the ENTSO-E "
            "series and is marked incomplete.",
            "",
            "## Missing values",
            "",
            "| Column | Missing intervals |",
            "|---|---|",
            *[f"| `{column}` | {count} |" for column, count in missing.items()],
            "",
            "## Columns",
            "",
            "| Column | Unit |",
            "|---|---|",
            *[f"| `{column}` | {UNITS[column]} |" for column in ALIGNED_COLUMNS],
            "",
            "## Reproduce",
            "",
            "```powershell",
            f".venv\\Scripts\\python.exe scripts/build_dataset.py --pv-source {args.pv_source}",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the aligned 15-minute dataset.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/farm.yaml")
    parser.add_argument("--eval-config", type=Path, default=ROOT / "configs/eval.yaml")
    parser.add_argument(
        "--pv-model-config", type=Path, default=ROOT / "configs/pv_model.yaml"
    )
    parser.add_argument(
        "--price-csv", type=Path, default=PROCESSED / "opcom_pzu_2026.csv"
    )
    parser.add_argument("--load-csv", type=Path, default=PROCESSED / "ENTSO_15MIN.csv")
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--output", type=Path, default=DATASET_PATH)
    parser.add_argument("--splits", type=Path, default=SPLITS_PATH)
    parser.add_argument("--meta", type=Path, default=PROCESSED / "dataset_meta.json")
    parser.add_argument("--data-card", type=Path, default=PROCESSED / "data_card.md")
    parser.add_argument(
        "--validation", type=Path, default=PROCESSED / "validation_report.json"
    )
    parser.add_argument(
        "--pv-source",
        choices=("auto", "metered", "open-meteo", "pvgis", "clear-sky"),
        default="auto",
    )
    parser.add_argument("--metered-pv", type=Path, default=None)
    parser.add_argument("--pvgis-year", type=int, default=2023)
    parser.add_argument(
        "--cache-dir", type=Path, default=ROOT / "artifacts/data/raw/pv"
    )
    parser.add_argument("--performance-ratio", type=float, default=0.85)
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="use the clear-sky source if the upstream fetch fails",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    meta = build(args)
    print(json.dumps({"rows": meta["rows"], "days": meta["days"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
