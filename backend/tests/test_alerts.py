"""Critical alerts, the ticketing webhook and the agent journal (ticket 20)."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes import mock as ticketing
from app.main import app
from app.schemas import AgentEvent, Alert, StreamEvent
from app.services import state
from app.services.decision import alerts
from app.services.missions import DEMOS
from tests import fakes
from tests.conftest import FAST, fly_to_end, read_stream

SCENARIO_1 = DEMOS["normal"].model_copy(update={"speed": FAST}).model_dump()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_ticketing():
    ticketing._tickets.clear()
    yield
    ticketing._tickets.clear()


@pytest.fixture
def sink(monkeypatch):
    """Point the webhook at the in-process mock receiver and keep its ticket list."""

    async def post(url: str, payload: dict) -> None:
        ticketing.receive_ticket(payload)

    monkeypatch.setattr(alerts, "_post", post)
    return ticketing._tickets


def analysed(client: TestClient) -> str:
    """A mission that flew and was analysed; returns its id."""
    mid = client.post("/api/missions", json=SCENARIO_1).json()["id"]
    fly_to_end(client, mid)
    assert client.post(f"/api/missions/{mid}/analyse").status_code == 200
    return mid


def deliveries(client: TestClient, mid: str) -> int:
    """Alerts + work orders: each one goes to the webhook once."""
    n_alerts = len(client.get(f"/api/missions/{mid}/alerts").json())
    return n_alerts + len(client.get(f"/api/missions/{mid}/work-orders").json())


def test_critical_finding_raises_an_alert_and_a_ticket(client, sink):
    mid = analysed(client)
    raised = [Alert.model_validate(a) for a in client.get(f"/api/missions/{mid}/alerts").json()]
    alert = next(a for a in raised if a.id == "AL-012")  # the hot cell of scenario 1
    assert (alert.finding_id, alert.level) == ("F-012", "critical")
    assert alert.message == "hot_cell cu ΔT 31,0 K pe B1-R5-T1-M11 (≥ 20 K)"
    assert alert.raised_at.endswith("Z")
    ids = [t["id"] for t in client.get("/api/mock/ticketing").json()]
    assert ids[: len(raised)] == [a.id for a in raised]  # alerts go before the work orders
    assert ids.count("WO-012") == 1
    state.drop(mid)


def test_non_critical_findings_raise_no_alert():
    findings = [f for f in fakes.findings() if f.id != "F-001"]
    assert alerts.raise_alerts(findings, "2026-11-07T10:00:00Z") == []


def test_safety_threshold_is_20k():
    hot = fakes.findings()[0]
    cool = hot.model_copy(update={"evidence": hot.evidence.model_copy(update={"delta_t_k": 19.9})})
    assert alerts.raise_alerts([cool], "2026-11-07T10:00:00Z") == []
    assert [a.id for a in alerts.raise_alerts([hot], "2026-11-07T10:00:00Z")] == ["AL-001"]


def test_webhook_is_retried_three_times_and_logged(monkeypatch, caplog):
    calls = []

    async def down(url: str, payload: dict) -> None:
        calls.append(url)
        raise httpx.ConnectError("ticketing down")

    monkeypatch.setattr(alerts, "_post", down)
    assert asyncio.run(alerts.send({"id": "AL-001"})) is False
    assert len(calls) == 3
    assert "attempt 3/3 failed" in caplog.text
    assert "failed after 3 attempts" in caplog.text


def test_webhook_succeeds_on_the_first_attempt(monkeypatch):
    calls = []

    async def up(url: str, payload: dict) -> None:
        calls.append(payload)

    monkeypatch.setattr(alerts, "_post", up)
    assert asyncio.run(alerts.send({"id": "WO-001"})) is True
    assert calls == [{"id": "WO-001"}]


def test_journal_records_the_alert_and_the_work_orders(client, sink):
    mid = analysed(client)
    body = client.get(f"/api/missions/{mid}/events").json()
    pairs = [(e.kind, e.ref) for e in (AgentEvent.model_validate(e) for e in body)]
    assert ("alert_raised", "AL-012") in pairs
    assert ("work_order_created", "WO-012") in pairs
    assert sum(kind == "webhook_sent" for kind, _ in pairs) == len(sink)
    state.drop(mid)


def test_failed_webhook_is_journaled(client, monkeypatch):
    async def down(url: str, payload: dict) -> None:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(alerts, "_post", down)
    mid = analysed(client)
    kinds = [e["kind"] for e in client.get(f"/api/missions/{mid}/events").json()]
    assert kinds.count("webhook_failed") == deliveries(client, mid)
    assert "webhook_sent" not in kinds
    state.drop(mid)


def test_acknowledge_flips_the_missions_alert(client, sink):
    mid = analysed(client)
    before = [Alert.model_validate(a) for a in client.get(f"/api/missions/{mid}/alerts").json()]
    assert not any(a.acknowledged for a in before)
    acked = Alert.model_validate(client.post("/api/alerts/AL-012/ack").json())
    assert acked.acknowledged is True
    after = [Alert.model_validate(a) for a in client.get(f"/api/missions/{mid}/alerts").json()]
    assert {a.id for a in after if a.acknowledged} == {"AL-012"}
    state.drop(mid)


def test_alerts_survive_a_restart(client, sink):
    mid = analysed(client)
    before = client.get(f"/api/missions/{mid}/alerts").json()
    state.clear()  # a restart empties the memory; SQLite keeps the alerts (Q17)
    with TestClient(app) as c:
        assert c.get(f"/api/missions/{mid}/alerts").json() == before
    state.drop(mid)


def test_analysis_streams_alert_raised(client, sink):
    mid = client.post("/api/missions", json=SCENARIO_1).json()["id"]
    lines = fly_to_end(client, mid)
    last = max(int(ln.removeprefix("id: ")) for ln in lines if ln.startswith("id: "))
    assert client.post(f"/api/missions/{mid}/analyse").status_code == 200
    events = [
        StreamEvent.model_validate_json(ln.removeprefix("data: "))
        for ln in read_stream(client, mid, last)
        if ln.startswith("data: ")
    ]
    assert [e.root.type for e in events][:2] == ["findings_ready", "alert_raised"]
    alert = events[1].root.data
    assert (alert.id, alert.finding_id) == ("AL-012", "F-012")  # the hot cell, first in flight
    state.drop(mid)
