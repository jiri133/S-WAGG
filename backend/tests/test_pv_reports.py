"""PV forecast training metrics and the /api/eval/pv endpoint."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.pv_reports import load_metrics

METRICS = {
    "model": "hgb-pv-v1",
    "version": "1",
    "trained_at_utc": "2026-11-07T19:32:06Z",
    "rows": 100,
    "features": ["ghi", "dni"],
    "farm": {"name": "seed-demo"},
    "splits": {
        "test": {
            "overall": {"n": 10, "mae": 0.1, "rmse": 0.2, "bias": 0.03},
            "persistence": {"n": 10, "mae": 0.4, "rmse": 0.5, "bias": 0.02},
            "by_lead": {
                "0-4h": {"n": 8, "mae": 0.1, "rmse": 0.2, "bias": 0.03},
                "4-8h": {"n": 2, "mae": 0.2, "rmse": 0.3, "bias": 0.01},
                "8-12h": {"n": 0, "mae": None, "rmse": None, "bias": None},
            },
        },
        "train": {
            "overall": {"n": 90, "mae": 0.05, "rmse": 0.1, "bias": 0.0},
            "persistence": {"n": 90, "mae": 0.3, "rmse": 0.4, "bias": 0.01},
            "by_lead": {"0-4h": {"n": 90, "mae": 0.05, "rmse": 0.1, "bias": 0.0}},
        },
    },
}


def write_metrics(root: Path) -> Path:
    path = root / "artifacts" / "models" / "pv" / "metrics.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(METRICS), encoding="utf-8")
    return path


def test_loads_overall_and_lead_metrics(tmp_path):
    report = load_metrics(write_metrics(tmp_path))

    assert (report.model, report.version, report.rows, report.n_features) == (
        "hgb-pv-v1",
        "1",
        100,
        2,
    )
    assert report.farm == "seed-demo"
    assert [s.split for s in report.splits] == ["train", "test"]

    train, test = report.splits
    assert (train.mae, train.rmse, train.bias, train.persistence_mae) == (
        0.05,
        0.1,
        0.0,
        0.3,
    )
    assert test.mae == 0.1
    assert test.persistence_mae == 0.4
    # Empty lead bins are dropped; the rest keep their order.
    assert [(lead.lead, lead.n) for lead in test.by_lead] == [("0-4h", 8), ("4-8h", 2)]
    assert test.by_lead[1].mae == 0.2


def test_endpoint_serves_metrics(tmp_path, monkeypatch):
    write_metrics(tmp_path)
    monkeypatch.setattr(settings, "rl_root", tmp_path)

    with TestClient(app) as client:
        res = client.get("/api/eval/pv")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["model"] == "hgb-pv-v1"
    assert body["splits"][1]["mae"] == 0.1


def test_endpoint_is_404_without_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "rl_root", tmp_path)

    with TestClient(app) as client:
        res = client.get("/api/eval/pv")

    assert res.status_code == 404
