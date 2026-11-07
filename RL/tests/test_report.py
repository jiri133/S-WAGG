"""Report tests: aggregation, regime tables, markdown and plot artefacts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from battery_rl.config import load_farm_config
from battery_rl.eval.metrics import METRIC_NAMES
from battery_rl.eval.report import (
    regime_frame,
    summary_frame,
    write_report,
    write_report_from_csv,
)
from battery_rl.eval.runner import DayResult, to_rows


def base_metrics(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {name: 0.0 for name in METRIC_NAMES}
    values.update(
        {
            "renewable_utilization": 1.0,
            "soc_min": 0.10,
            "soc_max": 0.90,
            "soc_end": 0.50,
            "llm_feasible_rate": None,
            "llm_invalid_rate": None,
            "llm_tool_calls": None,
            "llm_tokens": None,
            "llm_latency_s": None,
            "llm_cost_ron": None,
        }
    )
    values.update(overrides)
    return values


def make_result(
    day: str,
    strategy: str,
    mode: str,
    *,
    repeat: int = 0,
    score: float = 100.0,
    net: float = -10.0,
    regimes: tuple[str, ...] = ("high_price",),
    records: list[dict[str, object]] | None = None,
) -> DayResult:
    return DayResult(
        day=date.fromisoformat(day),
        strategy=strategy,
        mode=mode,
        repeat=repeat,
        score_ron=score,
        metrics=base_metrics(
            net_cost_ron=net,
            export_revenue_ron=-net,
            import_cost_ron=0.0,
            throughput_mwh=1.0,
            equivalent_cycles=0.05,
            self_consumption_ratio=0.2,
            grid_import_mwh=0.0,
            grid_export_mwh=1.0,
        ),
        regimes=regimes,
        records=records or [],
    )


def sample_records() -> list[dict[str, object]]:
    return [
        {
            "soc_next": 0.50,
            "price_ron_mwh": 100.0,
            "p_discharge_mw": 0.0,
            "p_charge_mw": 0.0,
        },
        {
            "soc_next": 0.52,
            "price_ron_mwh": 200.0,
            "p_discharge_mw": 1.0,
            "p_charge_mw": 0.0,
        },
        {
            "soc_next": 0.49,
            "price_ron_mwh": 300.0,
            "p_discharge_mw": 0.0,
            "p_charge_mw": 1.0,
        },
    ]


def sample_results() -> list[DayResult]:
    return [
        make_result("2026-08-01", "idle", "block", score=100.0, net=-10.0,
                    regimes=("low_price",)),
        make_result(
            "2026-08-01",
            "price_threshold",
            "block",
            score=200.0,
            net=-20.0,
            regimes=("high_price", "weekend"),
            records=sample_records(),
        ),
        make_result("2026-08-02", "idle", "block", score=110.0, net=-11.0,
                    regimes=("low_price",)),
        make_result(
            "2026-08-02",
            "price_threshold",
            "block",
            score=210.0,
            net=-21.0,
            regimes=("high_price", "weekend"),
        ),
    ]


def test_summary_frame_aggregates_by_strategy_and_mode() -> None:
    summary = summary_frame(to_rows(sample_results()))
    assert len(summary) == 2
    idle = summary[(summary["strategy"] == "idle") & (summary["mode"] == "block")]
    assert idle.iloc[0]["runs"] == 2
    assert idle.iloc[0]["days"] == 2
    assert idle.iloc[0]["score_mean"] == pytest.approx(105.0)


def test_regime_frame_has_all_and_tagged_rows() -> None:
    regimes = regime_frame(to_rows(sample_results()))
    assert regimes.iloc[0]["regime"] == "all"
    assert set(regimes["regime"]) == {"all", "low_price", "high_price", "weekend"}
    all_rows = regimes[regimes["regime"] == "all"]
    assert len(all_rows) == 2


def test_summary_frame_rejects_empty_rows() -> None:
    with pytest.raises(ValueError, match="no rows"):
        summary_frame([])


def test_write_report_creates_csv_plots_and_markdown(tmp_path: Path) -> None:
    results = sample_results()
    sample = [result for result in results if result.records]
    report_path = write_report(
        results,
        tmp_path,
        split="val",
        farm=load_farm_config(),
        repeats=1,
        sample_results=sample,
        skipped_days=("2026-10-02",),
    )

    assert report_path == tmp_path / "report.md"
    text = report_path.read_text(encoding="utf-8")
    assert "Evaluation report — val" in text
    assert "high_price" in text
    assert "price_threshold" in text
    assert "Skipped incomplete days: 2026-10-02" in text
    assert "MPC and OracleLP have identical actions" in text
    assert (tmp_path / "results.csv").exists()
    assert (tmp_path / "score_by_strategy.png").exists()
    assert (tmp_path / "soc_sample_day.png").exists()
    assert (tmp_path / "price_and_power.png").exists()


def test_write_report_from_csv(tmp_path: Path) -> None:
    results = sample_results()
    write_report(
        results,
        tmp_path,
        split="val",
        farm=load_farm_config(),
        repeats=1,
        plots=False,
    )
    csv_path = tmp_path / "results.csv"
    output_dir = tmp_path / "from_csv"
    report_path = write_report_from_csv(csv_path, output_dir)

    text = report_path.read_text(encoding="utf-8")
    assert "Evaluation report" in text
    assert "idle" in text
    assert (output_dir / "score_by_strategy.png").exists()
