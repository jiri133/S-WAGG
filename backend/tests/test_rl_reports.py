"""RL battery report aggregation and the /api/eval/rl endpoint."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.rl_reports import load_reports

HEADER = (
    "day,strategy,mode,repeat,score_ron,net_cost_ron,export_revenue_ron,"
    "self_consumption_ratio,throughput_mwh,equivalent_cycles,"
    "llm_feasible_rate,llm_invalid_rate,llm_tool_calls,llm_tokens,llm_latency_s,llm_cost_ron"
)


def write_split(root: Path, name: str, rows: list[str], metadata: dict | None = None) -> Path:
    split_dir = root / name
    split_dir.mkdir(parents=True)
    (split_dir / "results.csv").write_text(
        "\n".join([HEADER, *rows]) + "\n", encoding="utf-8"
    )
    if metadata is not None:
        (split_dir / "run_metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
    return split_dir


def test_aggregates_by_strategy_and_mode(tmp_path):
    write_split(
        tmp_path,
        "val",
        [
            "2026-01-01,idle,block,0,10,-10,10,0.0,0.0,0.0,,,,,,",
            "2026-01-02,idle,block,0,20,-20,20,0.0,0.0,0.0,,,,,,",
            "2026-01-01,llm,block,0,30,-30,32,0.2,18.0,1.0,1.0,0.0,6.0,1200.0,40.0,0.05",
            "2026-01-02,llm,block,0,50,-50,52,0.4,22.0,1.2,1.0,0.5,8.0,1400.0,60.0,0.07",
        ],
        {
            "repeats": 1,
            "seed": 42,
            "created_utc": "2026-11-08T03:35:30Z",
            "farm": {"name": "seed-demo"},
        },
    )

    report = load_reports(tmp_path)

    assert [s.split for s in report.splits] == ["val"]
    split = report.splits[0]
    assert (split.days, split.runs, split.repeats, split.seed) == (2, 4, 1, 42)
    assert split.farm == "seed-demo"

    idle, llm = split.results
    assert (idle.strategy, idle.mode) == ("idle", "block")
    assert idle.score_mean == 15.0
    assert idle.score_std == pytest.approx(7.0710678)
    assert idle.net_cost_mean == -15.0
    assert idle.feasible_rate is None

    assert llm.score_mean == 40.0
    assert llm.self_consumption_mean == pytest.approx(0.3)
    assert llm.throughput_mean == pytest.approx(20.0)
    assert llm.feasible_rate == 1.0
    assert llm.invalid_rate == 0.25
    assert llm.tokens_per_day == pytest.approx(1300.0)


def test_orders_splits_and_skips_dirs_without_csv(tmp_path):
    write_split(tmp_path, "test", ["2026-01-01,idle,block,0,1,-1,1,0,0,0,,,,,,"])
    write_split(tmp_path, "val", ["2026-01-01,idle,block,0,1,-1,1,0,0,0,,,,,,"])
    (tmp_path / "empty").mkdir()

    report = load_reports(tmp_path)

    assert [s.split for s in report.splits] == ["val", "test"]
    assert report.splits[0].repeats is None


def test_missing_reports_dir_is_empty(tmp_path):
    assert load_reports(tmp_path / "nope").splits == []


def test_endpoint_serves_reports(tmp_path, monkeypatch):
    reports = tmp_path / "artifacts" / "reports"
    write_split(reports, "val", ["2026-01-01,idle,block,0,10,-10,10,0,0,0,,,,,,"])
    monkeypatch.setattr(settings, "rl_root", tmp_path)

    with TestClient(app) as client:
        res = client.get("/api/eval/rl")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["splits"][0]["split"] == "val"
    assert body["splits"][0]["results"][0]["score_mean"] == 10.0
