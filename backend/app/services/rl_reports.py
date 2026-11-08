"""Read the battery evaluation reports written by ``RL/scripts/evaluate.py``.

Each split directory under ``RL/artifacts/reports`` holds ``results.csv`` (one row per
day and repeat) plus an optional ``run_metadata.json``. The UI only needs the
per (strategy, mode) means, so this module aggregates the CSV with the stdlib.
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from app.core.config import settings
from app.schemas.rl_eval import RlEvalReport, RlSplitReport, RlStrategyResult

STRATEGY_ORDER = ("idle", "rule_based", "price_threshold", "mpc", "oracle_lp", "llm")
MODE_ORDER = {"block": 0, "step": 1}
SPLIT_ORDER = ("val", "test", "train")


def load_reports(root: Path | None = None) -> RlEvalReport:
    """Aggregate every split directory that has a ``results.csv``."""
    base = root or settings.rl_root / "artifacts" / "reports"
    if not base.is_dir():
        return RlEvalReport(splits=[])
    found = {
        path.name: _read_split(path)
        for path in base.iterdir()
        if path.is_dir() and (path / "results.csv").exists()
    }
    order = {name: index for index, name in enumerate(SPLIT_ORDER)}
    names = sorted(found, key=lambda name: (order.get(name, len(order)), name))
    return RlEvalReport(splits=[found[name] for name in names])


def _read_split(split_dir: Path) -> RlSplitReport:
    with (split_dir / "results.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    meta = _read_metadata(split_dir / "run_metadata.json")

    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["strategy"], row["mode"])].append(row)

    results = [
        _summarise(strategy, mode, group)
        for (strategy, mode), group in sorted(
            groups.items(),
            key=lambda item: (
                STRATEGY_ORDER.index(item[0][0])
                if item[0][0] in STRATEGY_ORDER
                else len(STRATEGY_ORDER),
                MODE_ORDER.get(item[0][1], len(MODE_ORDER)),
                item[0][0],
            ),
        )
    ]
    farm = meta.get("farm") or {}
    return RlSplitReport(
        split=split_dir.name,
        days=len({row["day"] for row in rows}),
        runs=len(rows),
        repeats=meta.get("repeats"),
        seed=meta.get("seed"),
        created_utc=meta.get("created_utc"),
        farm=farm.get("name"),
        results=results,
    )


def _summarise(
    strategy: str, mode: str, rows: list[dict[str, str]]
) -> RlStrategyResult:
    scores = _values(rows, "score_ron")
    return RlStrategyResult(
        strategy=strategy,
        mode=mode,
        runs=len(rows),
        days=len({row["day"] for row in rows}),
        score_mean=statistics.fmean(scores),
        score_std=statistics.stdev(scores) if len(scores) > 1 else 0.0,
        net_cost_mean=_mean(rows, "net_cost_ron"),
        export_revenue_mean=_mean(rows, "export_revenue_ron"),
        throughput_mean=_mean(rows, "throughput_mwh"),
        cycles_mean=_mean(rows, "equivalent_cycles"),
        self_consumption_mean=_mean(rows, "self_consumption_ratio"),
        feasible_rate=_optional_mean(rows, "llm_feasible_rate"),
        invalid_rate=_optional_mean(rows, "llm_invalid_rate"),
        tool_calls_per_day=_optional_mean(rows, "llm_tool_calls"),
        tokens_per_day=_optional_mean(rows, "llm_tokens"),
        latency_s_per_day=_optional_mean(rows, "llm_latency_s"),
        cost_ron_per_day=_optional_mean(rows, "llm_cost_ron"),
    )


def _read_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _values(rows: list[dict[str, str]], key: str) -> list[float]:
    return [float(row[key]) for row in rows if row.get(key)]


def _mean(rows: list[dict[str, str]], key: str) -> float:
    values = _values(rows, key)
    return statistics.fmean(values) if values else 0.0


def _optional_mean(rows: list[dict[str, str]], key: str) -> float | None:
    values = _values(rows, key)
    return statistics.fmean(values) if values else None
