"""Tests use their own SQLite file and config dir, never dev data."""

import os
import tempfile
from pathlib import Path

# Must run before app.core.config is imported.
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="solartriage_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_ROOT / 'test.db').as_posix()}"
os.environ["RL_CONFIG_DIR"] = str(_TEST_ROOT / "configs")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

FAST = 1000.0  # flight speed in tests: the whole flight takes well under a second


@pytest.fixture(autouse=True)
def offline_webhook(monkeypatch):
    """Tests never touch the network: the webhook is a no-op unless a test overrides it."""
    from app.services.decision import alerts as alerting

    async def post(url: str, payload: dict) -> None:
        return None

    monkeypatch.setattr(alerting, "_post", post)


@pytest.fixture(autouse=True)
def fresh_reviews():
    """Reviews are stored in SQLite: every test starts without them."""
    yield
    from sqlmodel import Session, select

    from app.core.db import engine
    from app.models import FindingRow

    with Session(engine) as session:
        for row in session.exec(select(FindingRow)):
            row.data = {**row.data, "review": None, "review_note": None}
            session.add(row)
        session.commit()


def read_stream(client: TestClient, mission_id: str, last_event_id: int | None = None) -> list[str]:
    """Every SSE line, until the server closes the stream (the mission is idle again)."""
    headers = {} if last_event_id is None else {"Last-Event-ID": str(last_event_id)}
    with client.stream("GET", f"/api/missions/{mission_id}/stream", headers=headers) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        return list(res.iter_lines())


def fly_to_end(
    client: TestClient, mission_id: str, action: str = "fly", last_event_id: int | None = None
) -> list[str]:
    """POST fly/refly, then read the stream (after `last_event_id`) until the flight is over."""
    res = client.post(f"/api/missions/{mission_id}/{action}")
    assert res.status_code == 200, res.text
    assert res.json()["phase"] == "flying"
    return read_stream(client, mission_id, last_event_id)


def analysed_mission(client: TestClient) -> str:
    """A new mission with demo scenario 1's settings (seed 22), flown and analysed, webhook off.

    Its hot cell F-022 raises AL-022. Reviews name a finding without its mission, so they reach
    the mission analysed last.
    """
    from app.services.decision import alerts as alerting
    from app.services.missions import DEMOS

    async def post(url: str, payload: dict) -> None:
        return None

    body = DEMOS["normal"].model_copy(update={"speed": FAST}).model_dump()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(alerting, "_post", post)
        mid = client.post("/api/missions", json=body).json()["id"]
        fly_to_end(client, mid)
        assert client.post(f"/api/missions/{mid}/analyse").status_code == 200
    return mid


@pytest.fixture(scope="session", autouse=True)
def mission_m0001():
    """M-0001 = scenario 1, analysed: the mission the contract and endpoint tests read."""
    with TestClient(app) as c:
        assert analysed_mission(c) == "M-0001"
