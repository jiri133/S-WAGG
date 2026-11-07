#!/usr/bin/env python3
"""Run the Lane B baselines and the reference LPs on a split.

Example::

    cd RL
    uv run python scripts/evaluate.py --split val

The script writes ``results.csv``, plots and ``report.md`` under
``artifacts/reports/<split>/`` by default.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battery_rl.config import (  # noqa: E402
    load_env_config,
    load_eval_config,
    load_farm_config,
)
from battery_rl.data.dataset import load_split  # noqa: E402
from battery_rl.eval.report import summary_frame, write_report  # noqa: E402
from battery_rl.eval.runner import (  # noqa: E402
    StrategySpec,
    build_oracle_context,
    run_split,
    to_rows,
    usable_days,
)
from battery_rl.seeding import seed_everything  # noqa: E402
from battery_rl.strategies.idle import Idle  # noqa: E402
from battery_rl.strategies.mpc import MPC  # noqa: E402
from battery_rl.strategies.oracle_lp import OracleLP  # noqa: E402
from battery_rl.strategies.price_threshold import PriceThreshold  # noqa: E402
from battery_rl.strategies.rule_based import RuleBased  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("evaluate")
DEFAULT_STRATEGIES = "idle,rule_based,price_threshold,mpc,oracle_lp"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate merchant battery strategies.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/farm.yaml")
    parser.add_argument("--eval-config", type=Path, default=ROOT / "configs/eval.yaml")
    parser.add_argument("--split", default="val", choices=("train", "val", "test"))
    parser.add_argument("--strategies", default=DEFAULT_STRATEGIES)
    parser.add_argument("--repeats", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--limit-days", type=int, default=None)
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def build_specs(names: list[str]) -> list[StrategySpec]:
    specs: list[StrategySpec] = []
    for raw_name in names:
        name = raw_name.strip()
        if not name:
            continue
        if name == "idle":
            specs.append(
                StrategySpec("idle", lambda day, env: Idle(), ("step", "block"))
            )
        elif name == "rule_based":
            specs.append(
                StrategySpec(
                    "rule_based", lambda day, env: RuleBased(env.spec), ("step", "block")
                )
            )
        elif name == "price_threshold":
            specs.append(
                StrategySpec(
                    "price_threshold",
                    lambda day, env: PriceThreshold(env.spec, prices=day.price_ron_mwh),
                    ("step", "block"),
                )
            )
        elif name == "mpc":
            specs.append(StrategySpec("mpc", lambda day, env: MPC(), ("block",)))
        elif name == "oracle_lp":
            specs.append(
                StrategySpec(
                    "oracle_lp",
                    lambda day, env: OracleLP(),
                    ("block",),
                    context_builder=build_oracle_context,
                )
            )
        elif name == "llm":
            LOGGER.warning(
                "LLM is Lane A; add it through eval.runner.StrategySpec once "
                "agents/llm.py exists. Skipping 'llm'."
            )
        else:
            raise SystemExit(f"unknown strategy: {name!r}")
    return specs


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    farm = load_farm_config(args.config)
    env_config = load_env_config()
    eval_config = load_eval_config(args.eval_config)
    repeats = args.repeats if args.repeats is not None else eval_config.repeats
    seed = args.seed if args.seed is not None else eval_config.seed
    seed_everything(seed)

    days = load_split(args.split)
    complete_days = usable_days(days)
    skipped_names = sorted(
        day.day.isoformat() for day in days if not bool(day.is_complete.all())
    )
    if skipped_names:
        LOGGER.warning(
            "skipping %d incomplete delivery day(s): %s",
            len(skipped_names),
            ", ".join(skipped_names),
        )
    days = complete_days
    if args.limit_days is not None:
        days = days[: args.limit_days]
    if not days:
        raise SystemExit(f"split {args.split!r} has no complete days")

    specs = build_specs(args.strategies.split(","))
    if not specs:
        raise SystemExit("no strategies selected")

    output_dir = (
        Path(args.output_dir)
        if args.output_dir is not None
        else ROOT / eval_config.output_dir / args.split
    )
    LOGGER.info(
        "evaluating %d days x %d strategies x %d repeats -> %s",
        len(days),
        len(specs),
        repeats,
        output_dir,
    )
    results = run_split(
        days,
        specs,
        farm=farm,
        env_config=env_config,
        repeats=repeats,
        keep_records=False,
    )
    sample_results = None
    if not args.no_plots:
        sample_results = run_split(
            days[:1],
            specs,
            farm=farm,
            env_config=env_config,
            repeats=1,
            keep_records=True,
        )
    report_path = write_report(
        results,
        output_dir,
        split=args.split,
        farm=farm,
        repeats=repeats,
        sample_results=sample_results,
        plots=not args.no_plots,
        skipped_days=skipped_names,
    )

    summary = summary_frame(to_rows(results))
    print(summary.to_string(index=False))
    print(f"\nreport: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
