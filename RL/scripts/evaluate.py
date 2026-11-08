#!/usr/bin/env python3
"""Run the merchant baselines, reference LPs and the LLM agent on a split.

Example::

    cd RL
    uv run python scripts/evaluate.py --split val

The script writes ``results.csv``, plots and ``report.md`` under
``artifacts/reports/<split>/`` by default.  ``llm`` is included by default and
skipped with a warning when ``DEEPSEEK_API_KEY`` is not configured.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battery_rl.agents.llm import DeepSeekClient, LLMAgent  # noqa: E402
from battery_rl.agents.simulator import ContextSimulator  # noqa: E402
from battery_rl.config import (  # noqa: E402
    EnvConfig,
    FarmConfig,
    load_agent_config,
    load_env_config,
    load_eval_config,
    load_farm_config,
)
from battery_rl.credentials import MissingSecretError  # noqa: E402
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
DEFAULT_STRATEGIES = "idle,rule_based,price_threshold,mpc,oracle_lp,llm"


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
    parser.add_argument(
        "--transcript-dir",
        type=Path,
        default=None,
        help="Directory for per-decision LLM JSONL transcripts (default: <output>/transcripts).",
    )
    parser.add_argument(
        "--no-transcripts",
        action="store_true",
        help="Do not write LLM decision transcripts.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Replay existing transcripts and call the LLM only for missing "
            "day/mode/repeat combinations."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Evaluate this many delivery days concurrently (LLM evaluation).",
    )
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def build_specs(
    names: list[str],
    farm: FarmConfig,
    env_config: EnvConfig,
) -> list[StrategySpec]:
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
            try:
                agent_config = load_agent_config()
                client = DeepSeekClient.from_config(agent_config)
            except (MissingSecretError, RuntimeError) as exc:
                LOGGER.warning("LLM skipped: %s", exc)
                continue
            simulator = ContextSimulator(
                dt_h=env_config.step_minutes / 60.0,
                violation_penalty_ron_per_mwh=(
                    env_config.objective.violation_penalty_ron_per_mwh
                ),
            )

            def llm_factory(
                day,
                env,
                config=agent_config,
                llm_client=client,
                sim=simulator,
                levels=env_config.action_levels,
            ):
                return LLMAgent(
                    config,
                    client=llm_client,
                    simulator=sim,
                    action_levels=levels,
                    fallback=lambda context, steps: RuleBased(env.spec).plan(
                        context, steps
                    ),
                )

            specs.append(StrategySpec("llm", llm_factory, ("block",)))
        else:
            raise SystemExit(f"unknown strategy: {name!r}")
    return specs


def write_run_metadata(
    output_dir: Path,
    *,
    args: argparse.Namespace,
    farm: FarmConfig,
    specs: list[StrategySpec],
    days: int,
    repeats: int,
    seed: int,
    transcript_dir: Path | None,
) -> Path:
    """Record model/prompt/config identity next to the results for reproducibility."""
    agent_config = None
    if any(spec.label == "llm" for spec in specs):
        agent_config = load_agent_config()
    payload = {
        "created_utc": datetime.now(UTC).isoformat(),
        "split": args.split,
        "days": days,
        "repeats": repeats,
        "workers": args.workers,
        "seed": seed,
        "limit_days": args.limit_days,
        "strategies": [spec.label for spec in specs],
        "farm": {
            "name": farm.name,
            "asset_scale": farm.asset_scale,
            "checksum": farm.checksum(),
        },
        "transcripts": str(transcript_dir) if transcript_dir is not None else None,
        "llm": (
            {
                "requested_model_id": agent_config.model_id,
                "provider": agent_config.provider,
                "prompt_version": agent_config.prompt_version,
                "replan_steps": agent_config.replan_steps,
                "execution_steps": agent_config.execution_steps,
                "planning_horizon": agent_config.planning_horizon,
                "max_simulator_calls": agent_config.max_simulator_calls,
                "max_output_tokens": agent_config.max_output_tokens,
                "max_retries": agent_config.max_retries,
                "request_timeout_s": agent_config.request_timeout_s,
                "client_max_retries": agent_config.client_max_retries,
                "pricing": agent_config.pricing.model_dump(mode="json"),
            }
            if agent_config is not None
            else None
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "run_metadata.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

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

    specs = build_specs(args.strategies.split(","), farm, env_config)
    if not specs:
        raise SystemExit("no strategies selected")

    output_dir = (
        Path(args.output_dir)
        if args.output_dir is not None
        else ROOT / eval_config.output_dir / args.split
    )
    transcript_dir = None
    if not args.no_transcripts:
        transcript_dir = (
            Path(args.transcript_dir)
            if args.transcript_dir is not None
            else output_dir / "transcripts"
        )
    if args.resume and transcript_dir is None:
        raise SystemExit("--resume requires transcripts; do not use --no-transcripts")
    prompt_version = None
    if any(spec.label == "llm" for spec in specs):
        prompt_version = load_agent_config().prompt_version
    LOGGER.info(
        "evaluating %d days x %d strategies x %d repeats -> %s",
        len(days),
        len(specs),
        repeats,
        output_dir,
    )
    if transcript_dir is not None:
        LOGGER.info(
            "LLM transcripts -> %s%s",
            transcript_dir,
            " (resume)" if args.resume else "",
        )
    metadata_path = write_run_metadata(
        output_dir,
        args=args,
        farm=farm,
        specs=specs,
        days=len(days),
        repeats=repeats,
        seed=seed,
        transcript_dir=transcript_dir,
    )
    LOGGER.info("run metadata -> %s", metadata_path)
    results = run_split(
        days,
        specs,
        farm=farm,
        env_config=env_config,
        repeats=repeats,
        keep_records=False,
        transcript_dir=transcript_dir,
        workers=args.workers,
        resume=args.resume,
        prompt_version=prompt_version,
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
            transcript_dir=transcript_dir,
            resume=args.resume,
            prompt_version=prompt_version,
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
