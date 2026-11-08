"""Evaluation reporting: aggregation, plots and ``report.md``.

The report aggregates the runner's per-day CSV by strategy/mode and by data-derived regime,
and (when the in-memory results carry step records) plots SoC and price/power for a sample
day.  ``write_report_from_csv`` produces the same summary tables from a saved CSV.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from battery_rl.config import FarmConfig
from battery_rl.eval.runner import REGIMES, DayResult, to_rows, write_csv

SUMMARY_COLUMNS = (
    "Strategy",
    "Mode",
    "Runs",
    "Days",
    "Score mean",
    "Score std",
    "Net cost mean",
    "Export rev mean",
    "Throughput mean",
    "Cycles mean",
    "Self-cons mean",
)

REGIME_COLUMNS = (
    "Regime",
    "Strategy",
    "Mode",
    "Runs",
    "Score mean",
    "Net cost mean",
    "Export rev mean",
    "Throughput mean",
    "Self-cons mean",
)

LLM_COLUMNS = (
    "Strategy",
    "Mode",
    "Runs",
    "Feasible rate",
    "Invalid rate",
    "Tool calls/day",
    "Tokens/day",
    "Latency/day (s)",
    "Cost/day (RON)",
)


def write_report(
    results: Sequence[DayResult],
    output_dir: str | Path,
    *,
    split: str,
    farm: FarmConfig,
    repeats: int,
    sample_results: Sequence[DayResult] | None = None,
    plots: bool = True,
    skipped_days: Sequence[str] = (),
) -> Path:
    """Write ``results.csv``, plots and ``report.md``; return the report path."""
    if not results:
        raise ValueError("at least one result is required")
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    rows = to_rows(results)
    csv_path = write_csv(results, target / "results.csv")

    summary = summary_frame(rows)
    regimes = regime_frame(rows)

    plot_paths: list[Path] = []
    if plots:
        plot_paths.append(plot_score_summary(rows, target / "score_by_strategy.png"))
        if sample_results:
            plot_paths.append(plot_soc_sample(sample_results, target / "soc_sample_day.png"))
            plot_paths.append(
                plot_price_and_power(sample_results, target / "price_and_power.png")
            )

    lines = [
        f"# Evaluation report — {split}",
        "",
        "## Scope",
        "",
        f"- Split: **{split}**",
        f"- Farm: **{farm.name}** (`s={farm.asset_scale:g}`, checksum `{farm.checksum()[:12]}…`)",
        f"- Repeats per day: **{repeats}**",
        f"- Days: **{len({result.day for result in results})}**",
        f"- Runs: **{len(results)}**",
        f"- Per-day CSV: `{csv_path.name}`",
    ]
    if skipped_days:
        lines.append(f"- Skipped incomplete days: {', '.join(skipped_days)}")
    if (target / "run_metadata.json").exists():
        lines.append("- Run metadata: `run_metadata.json`")
    lines.extend(
        [
            "",
            "Score is the full merchant objective: −cash flow − degradation − violations +",
            "terminal value. Net cost is cash flow only (negative = revenue).",
            "",
            "MPC and OracleLP have identical actions here: with known D-1 prices, zero site",
            "demand and no export limit, the dispatch LP is price-only. The oracle differs",
            "only in using actual future PV for the reported objective; it is the upper bound.",
            "",
            "## By strategy and mode",
            "",
            _markdown_table(
            SUMMARY_COLUMNS,
            [
                (
                    row["strategy"],
                    row["mode"],
                    int(row["runs"]),
                    int(row["days"]),
                    _fmt(row["score_mean"]),
                    _fmt(row["score_std"]),
                    _fmt(row["net_cost_mean"]),
                    _fmt(row["export_revenue_mean"]),
                    _fmt(row["throughput_mean"], 3),
                    _fmt(row["cycles_mean"], 3),
                    _fmt(row["self_consumption_mean"], 3),
                )
                for _, row in summary.iterrows()
            ],
        ),
        "",
        *_llm_section(rows),
        *_gap_section(rows),
        "## By regime",
        "",
        "Regimes are split terciles: high/low mean price, high price volatility, high/low",
        "daily PV energy, plus weekends. A day can be in several regimes; `all` is the",
        "full split.",
        "",
        _markdown_table(
            REGIME_COLUMNS,
            [
                (
                    row["regime"],
                    row["strategy"],
                    row["mode"],
                    int(row["runs"]),
                    _fmt(row["score_mean"]),
                    _fmt(row["net_cost_mean"]),
                    _fmt(row["export_revenue_mean"]),
                    _fmt(row["throughput_mean"], 3),
                    _fmt(row["self_consumption_mean"], 3),
                )
                for _, row in regimes.iterrows()
            ],
        ),
    ]
    )
    if plots and plot_paths:
        lines.extend(["", "## Plots", ""])
        for path in plot_paths:
            lines.append(f"![{path.stem}]({path.name})")
            lines.append("")
    report_path = target / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def write_report_from_csv(
    csv_path: str | Path,
    output_dir: str | Path,
    *,
    plots: bool = True,
) -> Path:
    """Build ``report.md`` from a saved per-day CSV (no step records needed)."""
    frame = pd.read_csv(csv_path)
    rows = frame.to_dict("records")
    if not rows:
        raise ValueError(f"{csv_path} contains no rows")
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    summary = summary_frame(rows)
    regimes = regime_frame(rows)

    plot_paths: list[Path] = []
    if plots:
        plot_paths.append(plot_score_summary(rows, target / "score_by_strategy.png"))

    lines = [
        "# Evaluation report",
        "",
        f"- Source CSV: `{Path(csv_path).name}`",
        f"- Runs: **{len(rows)}**",
        f"- Days: **{len({row['day'] for row in rows})}**",
        *(
            ["- Run metadata: `run_metadata.json`"]
            if (target / "run_metadata.json").exists()
            else []
        ),
        "",
        "Score is the full merchant objective: −cash flow − degradation − violations +",
        "terminal value. Net cost is cash flow only (negative = revenue).",
        "",
        "MPC and OracleLP have identical actions under the merchant balance: the dispatch",
        "LP is price-only because prices are known D-1 and PV is a cash-flow constant.",
        "",
        "## By strategy and mode",
        "",
        _markdown_table(
            SUMMARY_COLUMNS,
            [
                (
                    row["strategy"],
                    row["mode"],
                    int(row["runs"]),
                    int(row["days"]),
                    _fmt(row["score_mean"]),
                    _fmt(row["score_std"]),
                    _fmt(row["net_cost_mean"]),
                    _fmt(row["export_revenue_mean"]),
                    _fmt(row["throughput_mean"], 3),
                    _fmt(row["cycles_mean"], 3),
                    _fmt(row["self_consumption_mean"], 3),
                )
                for _, row in summary.iterrows()
            ],
        ),
        "",
        *_llm_section(rows),
        *_gap_section(rows),
        "## By regime",
        "",
        _markdown_table(
            REGIME_COLUMNS,
            [
                (
                    row["regime"],
                    row["strategy"],
                    row["mode"],
                    int(row["runs"]),
                    _fmt(row["score_mean"]),
                    _fmt(row["net_cost_mean"]),
                    _fmt(row["export_revenue_mean"]),
                    _fmt(row["throughput_mean"], 3),
                    _fmt(row["self_consumption_mean"], 3),
                )
                for _, row in regimes.iterrows()
            ],
        ),
    ]
    if plots and plot_paths:
        lines.extend(["", "## Plots", ""])
        for path in plot_paths:
            lines.append(f"![{path.stem}]({path.name})")
            lines.append("")
    report_path = target / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def summary_frame(rows: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """Mean/std of the primary metrics by (strategy, mode)."""
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("no rows to aggregate")
    summary = (
        frame.groupby(["strategy", "mode"], dropna=False)
        .agg(
            runs=("day", "size"),
            days=("day", "nunique"),
            score_mean=("score_ron", "mean"),
            score_std=("score_ron", "std"),
            net_cost_mean=("net_cost_ron", "mean"),
            export_revenue_mean=("export_revenue_ron", "mean"),
            throughput_mean=("throughput_mwh", "mean"),
            cycles_mean=("equivalent_cycles", "mean"),
            self_consumption_mean=("self_consumption_ratio", "mean"),
        )
        .reset_index()
    )
    summary["score_std"] = summary["score_std"].fillna(0.0)
    return summary


def regime_frame(rows: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """Mean metrics for ``all`` and for every tagged regime."""
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("no rows to aggregate")
    frame["regimes"] = frame["regimes"].fillna("").astype(str)

    all_rows = frame.copy()
    all_rows["regime"] = "all"

    exploded = frame.copy()
    exploded["regime"] = exploded["regimes"].str.split("|")
    exploded = exploded.explode("regime")
    exploded = exploded[exploded["regime"].astype(bool)]
    if not exploded.empty:
        exploded["regime"] = exploded["regime"].astype(str)

    combined = pd.concat([all_rows, exploded], ignore_index=True)
    grouped = (
        combined.groupby(["regime", "strategy", "mode"], dropna=False)
        .agg(
            runs=("day", "size"),
            score_mean=("score_ron", "mean"),
            net_cost_mean=("net_cost_ron", "mean"),
            export_revenue_mean=("export_revenue_ron", "mean"),
            throughput_mean=("throughput_mwh", "mean"),
            self_consumption_mean=("self_consumption_ratio", "mean"),
        )
        .reset_index()
    )
    order = {name: index for index, name in enumerate(("all", *REGIMES))}
    grouped["_order"] = grouped["regime"].map(order).fillna(len(order))
    return grouped.sort_values(["_order", "strategy", "mode"]).drop(columns="_order")


def _llm_section(rows: Sequence[dict[str, Any]]) -> list[str]:
    """Markdown section with the LLM feasibility/token/latency/cost table."""
    frame = pd.DataFrame(rows)
    if "llm_feasible_rate" not in frame.columns:
        return []
    llm = frame[frame["llm_feasible_rate"].notna()]
    if llm.empty:
        return []
    grouped = (
        llm.groupby(["strategy", "mode"], dropna=False)
        .agg(
            runs=("day", "size"),
            feasible=("llm_feasible_rate", "mean"),
            invalid=("llm_invalid_rate", "mean"),
            tool_calls=("llm_tool_calls", "mean"),
            tokens=("llm_tokens", "mean"),
            latency=("llm_latency_s", "mean"),
            cost=("llm_cost_ron", "mean"),
        )
        .reset_index()
    )
    return [
        "## LLM telemetry",
        "",
        "Mean per day per run. A 96-interval day has six decisions; a 100-interval DST",
        "day has seven. Cost uses the provider rates recorded in `configs/agent.yaml`",
        "(`pricing`). Feasibility is measured after validation; the invalid rate is",
        "measured before fallback.",
        "",
        _markdown_table(
            LLM_COLUMNS,
            [
                (
                    row["strategy"],
                    row["mode"],
                    int(row["runs"]),
                    _pct(row["feasible"]),
                    _pct(row["invalid"]),
                    _fmt(row["tool_calls"], 2),
                    f"{float(row['tokens']):,.0f}",
                    _fmt(row["latency"], 1),
                    _fmt(row["cost"], 4),
                )
                for _, row in grouped.iterrows()
            ],
        ),
        "",
    ]


def _gap_section(rows: Sequence[dict[str, Any]]) -> list[str]:
    """Markdown table with the LLM's score gap to each reference strategy."""
    frame = pd.DataFrame(rows)
    if "strategy" not in frame.columns or "llm" not in set(frame["strategy"]):
        return []
    block = frame[frame["mode"] == "block"]
    llm_rows = block[block["strategy"] == "llm"]
    if llm_rows.empty or llm_rows["score_ron"].isna().all():
        return []
    llm_score = float(llm_rows["score_ron"].mean())
    table_rows: list[tuple[str, str, str, str]] = []
    for reference in ("idle", "rule_based", "price_threshold", "mpc", "oracle_lp"):
        reference_rows = block[block["strategy"] == reference]
        if reference_rows.empty or reference_rows["score_ron"].isna().all():
            continue
        reference_score = float(reference_rows["score_ron"].mean())
        gap = (
            (llm_score - reference_score) / abs(reference_score) * 100.0
            if reference_score
            else None
        )
        table_rows.append(
            (
                reference,
                f"{llm_score:,.2f}",
                f"{reference_score:,.2f}",
                f"{gap:+.1f}%" if gap is not None else "—",
            )
        )
    if not table_rows:
        return []
    return [
        "## LLM vs reference strategies",
        "",
        "Block mode; score is the full merchant objective (higher is better). The gap",
        "is relative to the reference. `rule_based` here is block mode; its step-mode",
        "score is in the main table.",
        "",
        _markdown_table(
            ("Reference", "LLM score", "Reference score", "Gap"),
            table_rows,
        ),
        "",
    ]


def plot_score_summary(rows: Sequence[dict[str, Any]], path: str | Path) -> Path:
    """Bar chart of mean episode score by strategy and mode."""
    frame = pd.DataFrame(rows)
    summary = (
        frame.groupby(["strategy", "mode"], dropna=False)["score_ron"]
        .agg(["mean", "std"])
        .reset_index()
    )
    labels = [f"{row.strategy}\n{row.mode}" for row in summary.itertuples()]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(max(6.0, 1.4 * len(labels)), 4.2))
    axis.bar(
        range(len(labels)),
        summary["mean"],
        yerr=summary["std"].fillna(0.0),
        capsize=4,
        color="#3b6ea5",
    )
    axis.set_xticks(range(len(labels)), labels, fontsize=8)
    axis.set_ylabel("mean episode score (RON)")
    axis.set_title("Merchant battery dispatch — mean score by strategy")
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(target, dpi=150)
    plt.close(figure)
    return target


def plot_soc_sample(sample_results: Sequence[DayResult], path: str | Path) -> Path:
    """SoC trajectory for every strategy on the first repeat of the sample day."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(9.0, 4.2))
    plotted = 0
    for result in sample_results:
        if result.repeat != 0 or not result.records:
            continue
        axis.plot(
            range(len(result.records)),
            [record["soc_next"] for record in result.records],
            label=f"{result.strategy}:{result.mode}",
            linewidth=1.4,
        )
        plotted += 1
    axis.set_xlabel("interval")
    axis.set_ylabel("state of charge")
    axis.set_ylim(0.0, 1.0)
    axis.set_title("Sample-day SoC")
    axis.grid(alpha=0.25)
    if plotted:
        axis.legend(fontsize=7, ncol=2)
    figure.tight_layout()
    figure.savefig(target, dpi=150)
    plt.close(figure)
    return target


def plot_price_and_power(sample_results: Sequence[DayResult], path: str | Path) -> Path:
    """Price and executed battery power for one sample strategy/day."""
    selected = next(
        (
            result
            for result in sample_results
            if result.records and (result.strategy, result.mode) == ("price_threshold", "block")
        ),
        None,
    )
    if selected is None:
        selected = next((result for result in sample_results if result.records), None)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if selected is None:
        return target

    steps = range(len(selected.records))
    prices = [record["price_ron_mwh"] for record in selected.records]
    power = [
        record["p_discharge_mw"] - record["p_charge_mw"] for record in selected.records
    ]
    figure, (price_axis, power_axis) = plt.subplots(
        2, 1, figsize=(9.0, 5.2), sharex=True
    )
    price_axis.plot(steps, prices, color="#b5651d", linewidth=1.3)
    price_axis.set_ylabel("price (RON/MWh)")
    price_axis.set_title(f"{selected.strategy}:{selected.mode} — price and executed power")
    price_axis.grid(alpha=0.25)
    power_axis.bar(steps, power, color="#3b6ea5", width=0.9)
    power_axis.axhline(0.0, color="black", linewidth=0.8)
    power_axis.set_xlabel("interval")
    power_axis.set_ylabel("power (MW, + discharge)")
    power_axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(target, dpi=150)
    plt.close(figure)
    return target


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "---|" * len(headers))
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{float(value):,.{digits}f}"


def _pct(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{float(value):.1%}"
