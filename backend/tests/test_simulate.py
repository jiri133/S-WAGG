"""Simulation endpoint tests; the RL subprocess is mocked."""

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import rl_simulation


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
