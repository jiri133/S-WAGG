"""Mission state, SSE and demo seeds (ticket 18)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Mission, MissionSettings, StreamEvent
from app.services import state
from app.services.sim import artefacts, compose
from app.services.sim.park import tables
from tests.conftest import FAST, fly_to_end, read_stream

MISSING = {"seed": 5, "inject": ["missing"], "speed": FAST}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def parse(lines: list[str]) -> list[tuple[int, StreamEvent]]:
    ids = [int(ln.removeprefix("id: ")) for ln in lines if ln.startswith("id: ")]
    events = [
        StreamEvent.model_validate_json(ln.removeprefix("data: "))
        for ln in lines
        if ln.startswith("data: ")
    ]
    assert len(ids) == len(events)
    return list(zip(ids, events, strict=True))


def types(events: list[tuple[int, StreamEvent]]) -> list[str]:
    return [e.root.type for _, e in events]


def create(client: TestClient, body: dict) -> str:
    res = client.post("/api/missions", json=body)
    assert res.status_code == 200
    m = Mission.model_validate(res.json())
    assert m.phase == "planned" and set(m.status.values()) == {"pending"} and m.truth is None
    return m.id


def missing_table(settings: MissionSettings) -> str:
    return next(f["table"] for f in artefacts.plan(settings) if f["inject"] == "missing")


def test_full_flight_streams_the_events_in_order(client):
    mid = create(client, MISSING)
    settings = MissionSettings(**MISSING)
    events = parse(fly_to_end(client, mid))

    assert [i for i, _ in events] == list(range(len(events)))
    seq = types(events)
    frames = compose.frames(settings)
    assert seq.count("waypoint") == len(tables())
    assert seq.count("frame_captured") == seq.count("frame_checked") == len(frames)
    for k, t in enumerate(seq):
        if t == "frame_captured":
            assert seq[k + 1] == "frame_checked"
    # Frames arrive in flight order, each after the waypoint of its table.
    captured = [e.root.data for _, e in events if e.root.type == "frame_captured"]
    assert [f.id for f in captured] == [f.id for f in frames]
    flight_done = seq.index("flight_done")
    assert flight_done > max(k for k, t in enumerate(seq) if t == "frame_checked")
    assert events[flight_done][1].root.data.frames == len(frames)
    cloudy = sum(f["cloud"] and not f["lost"] for f in artefacts.plan(settings))
    assert seq.count("cloud") == cloudy > 0
    # The table without frames gets a re-fly proposal, after flight_done.
    gone = missing_table(settings)
    refly = [e.root.data for _, e in events[flight_done:] if e.root.type == "agent_event"]
    assert [(a.kind, a.ref) for a in refly] == [("refly_proposed", gone)]

    m = Mission.model_validate(client.get(f"/api/missions/{mid}").json())
    assert m.phase == "checked"
    for mod in m.modules:
        assert m.status[mod.id] == ("not_inspected" if mod.table == gone else "pending")
    assert len(client.get(f"/api/missions/{mid}/frames").json()) == len(frames)
    state.drop(mid)


def test_analyse_then_refly_follow_the_phases(client):
    mid = create(client, MISSING)
    assert client.post(f"/api/missions/{mid}/analyse").status_code == 409  # not flown yet
    last = parse(fly_to_end(client, mid))[-1][0]
    assert client.post(f"/api/missions/{mid}/fly").status_code == 409  # already flown

    m = Mission.model_validate(client.post(f"/api/missions/{mid}/analyse").json())
    assert m.phase == "analysed" and "pending" not in m.status.values()
    gone = missing_table(MissionSettings(**MISSING))
    assert {m.status[x.id] for x in tables()[gone]} == {"not_inspected"}
    after = parse(read_stream(client, mid, last))
    assert after[0][0] == last + 1
    # Analysis streams the findings, the critical alert, then one journal line per delivery.
    assert types(after)[:2] == ["findings_ready", "alert_raised"]
    assert types(after).count("agent_event") == 10

    refly = parse(fly_to_end(client, mid, "refly", after[-1][0]))
    assert types(refly)[0] == "waypoint" and refly[0][1].root.data.table == gone
    assert types(refly)[-1] == "flight_done" and refly[-1][1].root.data.frames == 2
    m = Mission.model_validate(client.get(f"/api/missions/{mid}").json())
    assert m.phase == "checked"
    assert {m.status[x.id] for x in tables()[gone]} == {"pending"}
    assert client.post(f"/api/missions/{mid}/refly").status_code == 409  # nothing left
    state.drop(mid)


def test_history_has_every_event_type(client):
    mid = create(client, MISSING)
    fly_to_end(client, mid)
    client.post(f"/api/missions/{mid}/analyse")
    assert set(types(parse(read_stream(client, mid)))) == {
        "waypoint",
        "frame_captured",
        "frame_checked",
        "cloud",
        "flight_done",
        "findings_ready",
        "alert_raised",
        "agent_event",
    }
    state.drop(mid)


def test_state_survives_a_restart():
    with TestClient(app) as c:
        mid = create(c, MISSING)
        fly_to_end(c, mid)
        before = c.get(f"/api/missions/{mid}").json()
        frames = c.get(f"/api/missions/{mid}/frames").json()
    state.clear()  # a restart empties the memory; SQLite stays
    with TestClient(app) as c:
        assert c.get(f"/api/missions/{mid}").json() == before
        assert c.get(f"/api/missions/{mid}/frames").json() == frames
        assert before["phase"] == "checked"
        # The flight's events were in memory: a new stream starts empty and waits for the next
        # action, which the analysis provides.
        c.post(f"/api/missions/{mid}/analyse")
        assert types(parse(read_stream(c, mid, 99)))[:2] == ["findings_ready", "alert_raised"]
    state.drop(mid)


def test_interrupted_flight_is_back_to_planned():
    with TestClient(app) as c:
        mid = create(c, {"speed": 0.01})
        assert c.post(f"/api/missions/{mid}/fly").json()["phase"] == "flying"
    state.clear()
    with TestClient(app) as c:
        assert c.get(f"/api/missions/{mid}").json()["phase"] == "planned"


@pytest.mark.parametrize("scenario", ["normal", "bad_day", "explain"])
def test_demo_has_a_fixed_seed_and_resets(client, scenario):
    first = Mission.model_validate(client.post(f"/api/missions/demo/{scenario}").json())
    assert first.id == f"demo-{scenario}" and first.phase == "planned"
    assert first.truth == compose.truth(first.settings)
    assert client.post(f"/api/missions/{first.id}/fly").json()["phase"] == "flying"
    again = Mission.model_validate(client.post(f"/api/missions/demo/{scenario}").json())
    assert again == first  # same seed, the flight stopped and its progress dropped
    assert client.get(f"/api/missions/{first.id}/frames").json() == []
    state.drop(first.id)


def test_bad_day_hits_every_injection(client):
    mid = client.post("/api/missions/demo/bad_day").json()["id"]
    settings = Mission.model_validate(client.get(f"/api/missions/{mid}").json()).settings
    assert sorted(settings.inject) == sorted(artefacts.INJECTIONS)


def test_unknown_mission_or_scenario(client):
    assert client.get("/api/missions/M-9999").status_code == 404
    assert client.get("/api/missions/M-9999/stream").status_code == 404
    assert client.post("/api/missions/M-9999/fly").status_code == 404
    assert client.post("/api/missions/demo/nope").status_code == 422
