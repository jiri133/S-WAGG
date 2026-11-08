#!/usr/bin/env python3
"""Rebuild ``report.md`` and the summary plot from a saved results CSV.

Example::

    cd RL
    uv run python scripts/make_report.py --csv artifacts/reports/val/results.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battery_rl.eval.report import write_report_from_csv  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a markdown report from results.csv.")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to the CSV's parent directory.",
    )
    parser.add_argument("--no-plots", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir if args.output_dir is not None else args.csv.parent
    report_path = write_report_from_csv(
        args.csv, output_dir, plots=not args.no_plots
    )
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
