"""Bridge between the FastAPI layer and the RL planning runner.

The RL package lives in ``RL/`` with its own virtualenv and dependencies, so the
backend cannot import it. Instead it invokes ``rl_simulation_runner.py`` with the
RL interpreter and exchanges JSON over stdout.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

from app.core.config import settings


class SimulationError(RuntimeError):
    """A simulation failure that maps to an HTTP status code."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _resolve_rl_python() -> Path:
    configured = settings.rl_python
    if configured is not None:
        path = Path(configured)
        if path.exists():
            return path
        raise SimulationError(503, f"Interpretorul Python al RL nu a fost găsit: {path}")

    root = Path(settings.rl_root)
    for candidate in (root / ".venv/Scripts/python.exe", root / ".venv/bin/python"):
        if candidate.exists():
            return candidate
    raise SimulationError(
        503,
        "Mediul virtual RL nu a fost găsit. Rulează setup-ul RL "
        "(vezi RL/README.md) sau setează RL_PYTHON.",
    )


def run_simulation(
    *,
    strategy: str,
    split: str,
    day: date | None = None,
    seed: int | None = None,
    pv_factor: float = 1.0,
) -> dict:
    """Run one day in the RL virtualenv and return its JSON trace.

    ``pv_factor`` scales both actual and forecast PV (1.0 = untouched, 0.0 =
    no production). The inspection derate computes it in ``production``.
    """

    if not 0.0 <= pv_factor <= 1.0:
        raise SimulationError(422, "pv_factor trebuie să fie între 0 și 1")

    python = _resolve_rl_python()
    root = Path(settings.rl_root)
    config_dir = Path(settings.rl_config_dir)
    script = Path(__file__).with_name("rl_simulation_runner.py")

    command = [
        str(python),
        str(script),
        "--strategy",
        strategy,
        "--split",
        split,
        "--config",
        str(config_dir / "farm.yaml"),
        "--env-config",
        str(config_dir / "env.yaml"),
        "--agent-config",
        str(config_dir / "agent.yaml"),
        "--dataset",
        str(root / "artifacts/data/processed/aligned_2026.csv"),
        "--splits",
        str(root / "artifacts/data/processed/splits.json"),
    ]
    if day is not None:
        command.extend(["--day", day.isoformat()])
    if seed is not None:
        command.extend(["--seed", str(seed)])
    command.extend(["--pv-factor", str(pv_factor)])

    timeout = int(settings.simulation_timeout_s)
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SimulationError(504, f"Simularea a expirat după {timeout} secunde") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        if not detail:
            detail = f"Runner-ul RL s-a încheiat cu codul {completed.returncode}"
        raise SimulationError(502, detail[-1200:])

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SimulationError(502, "Runner-ul RL a returnat JSON invalid") from exc
    if not isinstance(payload, dict):
        raise SimulationError(502, "Runner-ul RL a returnat un payload neașteptat")
    return payload
