"""Simulation endpoint tests; the RL subprocess is mocked."""

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.simulation import SimulationDerate
from app.services import production, rl_simulation

RL_ROOT = Path(settings.rl_root)
RL_DATASET = RL_ROOT / "artifacts/data/processed/aligned_2026.csv"
RL_CONFIGS = RL_ROOT / "configs"


def _rl_ready() -> bool:
    try:
        rl_simulation._resolve_rl_python()
    except rl_simulation.SimulationError:
        return False
    return RL_DATASET.exists() and RL_CONFIGS.exists()


def payload() -> dict:
    return {
        "day": "2026-08-17",
        "split": "val",
        "strategy": "idle",
        "mode": "block",
        "farm": {"name": "seed-test", "asset_scale": 1.0},
        "summary": {"score_ron": 1.0, "intervals": 96},
        "decisions": [{"step_index": 0, "levels": [0.0]}],
        "steps": [{"interval": 1, "price_ron_mwh": 100.0}],
    }


def test_simulate_returns_trace(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload()), stderr=""
        )

    monkeypatch.setattr(rl_simulation, "_resolve_rl_python", lambda: Path("python"))
    monkeypatch.setattr(rl_simulation.subprocess, "run", fake_run)

    with TestClient(app) as client:
        res = client.post("/api/simulate", json={"strategy": "idle", "split": "val"})

    assert res.status_code == 200
    body = res.json()
    assert body["day"] == "2026-08-17"
    assert body["summary"]["intervals"] == 96
    command = calls[0][0]
    assert "--strategy" in command
    assert command[command.index("--strategy") + 1] == "idle"
    assert calls[0][1]["cwd"] == str(rl_simulation.settings.rl_root)


def test_simulate_passes_day_and_seed(monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload()), stderr=""
        )

    monkeypatch.setattr(rl_simulation, "_resolve_rl_python", lambda: Path("python"))
    monkeypatch.setattr(rl_simulation.subprocess, "run", fake_run)

    with TestClient(app) as client:
        res = client.post(
            "/api/simulate",
            json={"strategy": "mpc", "split": "test", "day": "2026-09-01", "seed": 7},
        )

    assert res.status_code == 200
    command = commands[0]
    assert command[command.index("--day") + 1] == "2026-09-01"
    assert command[command.index("--seed") + 1] == "7"
    assert command[command.index("--split") + 1] == "test"


def derate(factor: float = 0.5) -> SimulationDerate:
    return SimulationDerate(
        mission_id="M-0001",
        month=11,
        findings_total=3,
        findings_counted=2,
        findings_awaiting_review=1,
        findings_rejected=0,
        lost_kwh_day=10.0,
        park_kwh_day=562.32,
        factor=factor,
    )


def test_simulate_applies_the_inspection_derate(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload()), stderr=""
        )

    monkeypatch.setattr(rl_simulation, "_resolve_rl_python", lambda: Path("python"))
    monkeypatch.setattr(rl_simulation.subprocess, "run", fake_run)
    monkeypatch.setattr(production, "current", lambda session: derate(0.5))

    with TestClient(app) as client:
        res = client.post("/api/simulate", json={"strategy": "idle", "split": "val"})

    assert res.status_code == 200, res.text
    assert res.json()["derate"]["factor"] == 0.5
    command = calls[0]
    assert command[command.index("--pv-factor") + 1] == "0.5"


def test_derate_endpoint_returns_the_latest_impact(monkeypatch):
    monkeypatch.setattr(production, "current", lambda session: derate(0.98))

    with TestClient(app) as client:
        res = client.get("/api/simulate/derate")

    assert res.status_code == 200
    body = res.json()
    assert body["mission_id"] == "M-0001"
    assert body["factor"] == 0.98


def test_run_simulation_rejects_an_out_of_range_factor():
    with pytest.raises(rl_simulation.SimulationError):
        rl_simulation.run_simulation(strategy="idle", split="val", pv_factor=1.5)


@pytest.mark.skipif(
    not _rl_ready(), reason="RL virtualenv, dataset or configs are not available"
)
def test_pv_factor_scales_actual_and_forecast(monkeypatch):
    monkeypatch.setattr(settings, "rl_config_dir", RL_CONFIGS)

    full = rl_simulation.run_simulation(
        strategy="idle", split="val", day=date(2026, 8, 17), pv_factor=1.0
    )
    half = rl_simulation.run_simulation(
        strategy="idle", split="val", day=date(2026, 8, 17), pv_factor=0.5
    )

    assert full["summary"]["pv_energy_mwh"] == pytest.approx(
        2 * half["summary"]["pv_energy_mwh"]
    )
    assert full["summary"]["pv_peak_mw"] == pytest.approx(
        2 * half["summary"]["pv_peak_mw"]
    )
    assert full["steps"][0]["pv_mw"] == pytest.approx(2 * half["steps"][0]["pv_mw"])
    assert full["steps"][0]["pv_forecast_mw"] == pytest.approx(
        2 * half["steps"][0]["pv_forecast_mw"]
    )


def test_simulate_rejects_unknown_strategy():
    with TestClient(app) as client:
        res = client.post("/api/simulate", json={"strategy": "crystal_ball"})
    assert res.status_code == 422


def test_simulate_surfaces_runner_error(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 2, stdout="", stderr="DEEPSEEK_API_KEY is not set"
        )

    monkeypatch.setattr(rl_simulation, "_resolve_rl_python", lambda: Path("python"))
    monkeypatch.setattr(rl_simulation.subprocess, "run", fake_run)

    with TestClient(app) as client:
        res = client.post("/api/simulate", json={"strategy": "llm"})

    assert res.status_code == 502
    assert "DEEPSEEK_API_KEY" in res.json()["detail"]
