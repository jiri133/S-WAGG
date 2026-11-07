"""Tests use their own SQLite file, never backend/app.db."""

import os
import tempfile
from pathlib import Path

# Must run before app.core.config is imported.
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp()) / 'test.db').as_posix()}"

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


@pytest.fixture(scope="session", autouse=True)
def mission_m0001():
    """M-0001 with the default settings, flown: the mission the contract tests read."""
    with TestClient(app) as c:
        assert c.post("/api/missions", json={"speed": FAST}).json()["id"] == "M-0001"
        fly_to_end(c, "M-0001")
