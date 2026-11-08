"""Farm configuration API tests, including the RL contract and YAML export."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

RL_SRC = Path(__file__).resolve().parents[2] / "RL" / "src"
sys.path.insert(0, str(RL_SRC))

from battery_rl.config import load_farm_config  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.farm import FarmConfig  # noqa: E402


def payload(**overrides) -> dict:
    data = {
        "name": "seed-test",
        "latitude": 44.1598,
        "longitude": 28.6348,
        "pv_kwp": 6000.0,
        "inverter_ac_mw": 6.0,
        "tilt_deg": 30.0,
        "azimuth_deg": 180.0,
        "tracking": "none",
        "battery_capacity_mwh": 10.0,
        "battery_p_max_mw": 2.0,
        "soc_min": 0.1,
        "soc_max": 0.9,
        "eta_charge": 0.95,
        "eta_discharge": 0.95,
        "asset_scale": 1.0,
        "export_limit_mw": None,
        "import_limit_mw": None,
        "metered_pv_path": None,
        "timezone": "Europe/Bucharest",
        "notes": "test config",
    }
    data.update(overrides)
    return data


@pytest.fixture(autouse=True)
def clean_state():
    init_db()
    with Session(engine) as session:
        session.exec(delete(FarmConfig))
        session.commit()
    if settings.rl_config_dir.exists():
        for path in settings.rl_config_dir.glob("farm.yaml*"):
            path.unlink()
    yield


def test_create_activate_export_and_rl_contract() -> None:
    with TestClient(app) as client:
        created = client.post("/api/farms", json=payload())
        assert created.status_code == 201, created.text
        farm = created.json()
        assert farm["active"] is True  # first farm becomes active
        assert farm["scaled_pv_kwp"] == 6000.0
        assert farm["scaled_battery_capacity_mwh"] == 10.0
        assert farm["battery_pct_of_national_peak"] < 1.0

        active = client.get("/api/farms/active")
        assert active.status_code == 200
        assert active.json()["id"] == farm["id"]

        exported = client.post(f"/api/farms/{farm['id']}/activate")
        assert exported.status_code == 200, exported.text
        result = exported.json()
        assert result["checksum"]
        assert len(result["checksum"]) == 64
        config_path = Path(result["path"])
        assert config_path.name == "farm.yaml"
        assert config_path.exists()
        assert (config_path.parent / "farm.yaml.sha256").read_text().strip() == result["checksum"]

        rl_farm = load_farm_config(config_path)
        assert rl_farm.checksum() == result["checksum"]
        assert rl_farm.asset_scale == 1.0
        assert rl_farm.pv.kwp == 6000.0
        assert rl_farm.battery.capacity_mwh == 10.0
        assert rl_farm.grid.export_limit_mw is None


def test_second_farm_is_inactive_until_activated() -> None:
    with TestClient(app) as client:
        first = client.post("/api/farms", json=payload(name="first")).json()
        second = client.post(
            "/api/farms", json=payload(name="second", asset_scale=500.0)
        ).json()
        assert second["active"] is False

        activated = client.post(f"/api/farms/{second['id']}/activate")
        assert activated.status_code == 200
        result = activated.json()
        assert result["farm"]["active"] is True
        assert result["farm"]["asset_scale"] == 500.0

        farms = {item["id"]: item for item in client.get("/api/farms").json()}
        assert farms[first["id"]]["active"] is False
        assert farms[second["id"]]["active"] is True

        rl_farm = load_farm_config(result["path"])
        assert rl_farm.asset_scale == 500.0
        assert rl_farm.checksum() == result["checksum"]


def test_updating_active_farm_reexports() -> None:
    with TestClient(app) as client:
        farm = client.post("/api/farms", json=payload()).json()
        first_checksum = (settings.rl_config_dir / "farm.yaml.sha256").read_text().strip()

        updated = client.put(
            f"/api/farms/{farm['id']}",
            json=payload(asset_scale=250.0, notes="updated"),
        )
        assert updated.status_code == 200, updated.text
        second_checksum = (settings.rl_config_dir / "farm.yaml.sha256").read_text().strip()
        assert second_checksum != first_checksum

        rl_farm = load_farm_config(settings.rl_config_dir / "farm.yaml")
        assert rl_farm.asset_scale == 250.0
        assert rl_farm.checksum() == second_checksum


@pytest.mark.parametrize(
    "overrides",
    [
        {"asset_scale": 0},
        {"soc_min": 0.95},
        {"eta_charge": 0},
        {"latitude": 100},
        {"unexpected": "field"},
    ],
)
def test_invalid_payloads(overrides: dict) -> None:
    with TestClient(app) as client:
        response = client.post("/api/farms", json=payload(**overrides))
        assert response.status_code == 422


def test_missing_active_farm_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/farms/active")
        assert response.status_code == 404
