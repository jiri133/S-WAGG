#!/usr/bin/env python3
"""Run one trained-farm day and emit a JSON planning trace for the web UI.

This file lives in the backend tree so the web layer owns only frontend/backend
code, but it is executed by the RL virtualenv (the backend service invokes it as
a subprocess) because the backend service does not install the RL dependencies.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RL_ROOT = REPO_ROOT / "RL"
sys.path.insert(0, str(RL_ROOT / "src"))

from battery_rl.agents.llm import DeepSeekClient, LLMAgent
from battery_rl.agents.schemas import index_to_level
from battery_rl.agents.simulator import ContextSimulator
from battery_rl.config import load_agent_config, load_env_config, load_farm_config
from battery_rl.credentials import MissingSecretError
from battery_rl.data.dataset import DayData, load_days, load_split
from battery_rl.env.context import build_context_dict
from battery_rl.env.env import BatteryEnv
from battery_rl.eval.metrics import compute_day_metrics
from battery_rl.eval.runner import build_oracle_context, usable_days
from battery_rl.strategies.idle import Idle
from battery_rl.strategies.mpc import MPC
from battery_rl.strategies.oracle_lp import OracleLP
from battery_rl.strategies.price_threshold import PriceThreshold
from battery_rl.strategies.rule_based import RuleBased

LOGGER = logging.getLogger("rl_simulation_runner")


def _select_day(args: argparse.Namespace) -> tuple[DayData, str]:
    if args.day is not None:
        days = load_days(args.dataset)
        selected = days.get(args.day)
        if selected is None:
            raise SystemExit(f"Ziua {args.day.isoformat()} nu există în dataset")
        if not bool(selected.is_complete.all()):
            raise SystemExit(f"Ziua {args.day.isoformat()} are intervale lipsă în contract")
        return selected, "custom"

    days = load_split(
        args.split,
        dataset_path=args.dataset,
        splits_path=args.splits,
    )
    complete = usable_days(days)
    if not complete:
        raise SystemExit(f"Split-ul {args.split!r} nu are zile de livrare complete")
    rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    return rng.choice(complete), args.split


def _build_planner(args: argparse.Namespace, env: BatteryEnv, day: DayData):
    if args.strategy == "llm":
        agent_config = load_agent_config(args.agent_config)
        client = DeepSeekClient.from_config(agent_config)
        simulator = ContextSimulator(
            dt_h=env.config.step_minutes / 60.0,
            violation_penalty_ron_per_mwh=(
                env.objective.violation_penalty_ron_per_mwh
            ),
        )
        planner = LLMAgent(
            agent_config,
            client=client,
            simulator=simulator,
            action_levels=env.config.action_levels,
            fallback=lambda context, steps: RuleBased(env.spec).plan(context, steps),
        )
        return planner, build_context_dict, "llm", agent_config

    if args.strategy == "idle":
        return Idle(), build_context_dict, "idle", None
    if args.strategy == "rule_based":
        return RuleBased(env.spec), build_context_dict, "rule_based", None
    if args.strategy == "price_threshold":
        return (
            PriceThreshold(env.spec, prices=day.price_ron_mwh),
            build_context_dict,
            "price_threshold",
            None,
        )
    if args.strategy == "mpc":
        return MPC(), build_context_dict, "mpc", None
    if args.strategy == "oracle_lp":
        return OracleLP(), build_oracle_context, "oracle_lp", None
    raise SystemExit(f"Strategie necunoscută: {args.strategy!r}")


def _run(args: argparse.Namespace) -> dict:
    day, split_label = _select_day(args)
    if args.pv_factor != 1.0:
        day = replace(
            day,
            pv_mw=day.pv_mw * args.pv_factor,
            pv_forecast_mw=day.pv_forecast_mw * args.pv_factor,
        )
    farm = load_farm_config(args.config)
    env_config = load_env_config(args.env_config)
    env = BatteryEnv.from_farm(day, farm, env_config)
    env.reset()
    planner, context_builder, strategy_label, agent_config = _build_planner(
        args, env, day
    )

    steps: list[dict] = []
    decisions: list[dict] = []
    previous_plan: list[int] | None = None

    while not env.done:
        if context_builder is build_oracle_context:
            context = context_builder(env, farm)
        else:
            context = context_builder(env, farm, previous_plan=previous_plan)
        execution_steps = int(context["execution_steps"])

        if isinstance(planner, LLMAgent):
            result = planner.plan_with_metadata(context, execution_steps)
            actions = list(result.actions)
            decision = {
                "step_index": env.step_index,
                "time_utc": context["time_utc"],
                "execution_steps": execution_steps,
                "actions": actions,
                "levels": [float(index_to_level(action)) for action in actions],
                "rationale": result.rationale,
                "usage": result.usage,
                "valid": result.valid,
                "fallback": result.fallback,
                "error": result.error,
                "context": context,
            }
        else:
            actions = list(planner.plan(context, execution_steps))
            decision = {
                "step_index": env.step_index,
                "time_utc": context["time_utc"],
                "execution_steps": execution_steps,
                "actions": actions,
                "levels": [float(index_to_level(action)) for action in actions],
                "rationale": None,
                "usage": None,
                "valid": True,
                "fallback": False,
                "error": None,
                "context": context,
            }
        if len(actions) != execution_steps:
            raise SystemExit(
                f"Planificatorul a returnat {len(actions)} acțiuni, se așteptau {execution_steps}"
            )
        decisions.append(decision)

        for action in actions:
            index = env.step_index
            step = env.step(int(action))
            record = dict(step.info)
            record.update(
                {
                    "interval": index + 1,
                    "pv_forecast_mw": float(day.pv_forecast_mw[index]),
                    "action": int(action),
                    "level": float(index_to_level(int(action))),
                }
            )
            steps.append(record)
        previous_plan = actions

    telemetry = planner.telemetry if isinstance(planner, LLMAgent) else None
    metrics = compute_day_metrics(env.records, env.spec, llm=telemetry)
    summary = {
        "score_ron": env.episode_score_ron,
        **metrics,
        "decisions": len(decisions),
        "intervals": len(steps),
        "pv_energy_mwh": float(sum(float(value) for value in day.pv_mw) * 0.25),
        "pv_peak_mw": float(max(float(value) for value in day.pv_mw)),
        "mean_price_ron_mwh": float(
            sum(float(value) for value in day.price_ron_mwh) / day.intervals
        ),
        "model": agent_config.model_id if agent_config is not None else None,
        "prompt_version": (
            agent_config.prompt_version if agent_config is not None else None
        ),
    }
    return {
        "day": day.day.isoformat(),
        "split": split_label,
        "strategy": strategy_label,
        "mode": "block",
        "farm": {
            "name": farm.name,
            "checksum": farm.checksum(),
            "asset_scale": farm.asset_scale,
            "pv_kwp": farm.scaled_pv_kwp,
            "inverter_ac_mw": farm.scaled_inverter_ac_mw,
            "battery_capacity_mwh": farm.scaled_battery_capacity_mwh,
            "battery_p_max_mw": farm.scaled_p_max_mw,
        },
        "summary": summary,
        "decisions": decisions,
        "steps": steps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one trained-farm planning day.")
    parser.add_argument(
        "--strategy",
        choices=("llm", "mpc", "rule_based", "price_threshold", "idle", "oracle_lp"),
        default="idle",
    )
    parser.add_argument("--split", choices=("train", "val", "test"), default="val")
    parser.add_argument("--day", type=date.fromisoformat, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--pv-factor",
        type=float,
        default=1.0,
        help="Scale actual and forecast PV (1.0 untouched, 0.0 no production).",
    )
    parser.add_argument("--config", type=Path, default=RL_ROOT / "configs/farm.yaml")
    parser.add_argument("--env-config", type=Path, default=RL_ROOT / "configs/env.yaml")
    parser.add_argument(
        "--agent-config", type=Path, default=RL_ROOT / "configs/agent.yaml"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=RL_ROOT / "artifacts/data/processed/aligned_2026.csv",
    )
    parser.add_argument(
        "--splits",
        type=Path,
        default=RL_ROOT / "artifacts/data/processed/splits.json",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    if not 0.0 <= args.pv_factor <= 1.0:
        parser.error("--pv-factor trebuie să fie între 0 și 1")

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    try:
        payload = _run(args)
    except MissingSecretError as exc:
        print(f"Cheie API lipsă: {exc}", file=sys.stderr)
        return 2
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced to the web client
        LOGGER.exception("simularea a eșuat")
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    json.dump(payload, sys.stdout, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
