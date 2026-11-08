"""Every §9 endpoint answers with the shape of its Pydantic model."""


import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.main import app
from app.schemas import (
    AgentEvent,
    Alert,
    EvalReport,
    Finding,
    FrameMeta,
    Mission,
    Module,
    Plan,
    Prediction,
    WorkOrder,
)

M = "/api/missions/M-0001"  # demo scenario 1, flown and analysed in conftest.py
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


JSON_CASES = [
    ("get", "/api/park", None, list[Module]),
    ("post", "/api/missions", {"seed": 3}, Mission),
    ("post", "/api/missions/demo/normal", None, Mission),
    ("get", M, None, Mission),
    ("get", f"{M}/frames", None, list[FrameMeta]),
    ("get", f"{M}/findings", None, list[Finding]),
    ("post", "/api/findings/F-001/review", {"decision": "confirmed"}, Finding),
    ("get", f"{M}/work-orders", None, list[WorkOrder]),
    ("get", f"{M}/plan", None, Plan),
    ("get", f"{M}/alerts", None, list[Alert]),
    ("post", "/api/alerts/AL-012/ack", None, Alert),
    ("get", f"{M}/events", None, list[AgentEvent]),
    ("get", f"{M}/score", None, dict[str, int]),
    ("get", "/api/mock/ticketing", None, list[dict]),
    ("post", "/api/mock/ticketing", {"id": "WO-001"}, dict),
]


@pytest.mark.parametrize(("method", "path", "body", "model"), JSON_CASES)
def test_json_endpoint_matches_model(client, method, path, body, model):
    res = client.request(method.upper(), path, json=body)
    assert res.status_code == 200, res.text
    TypeAdapter(model).validate_python(res.json())


def test_park_layout(client):
    modules = TypeAdapter(list[Module]).validate_python(client.get("/api/park").json())
    assert len(modules) == 480
    assert len({m.id for m in modules}) == 480
    m = next(m for m in modules if m.id == "B1-R2-T3-M07")
    assert (m.table, m.string, m.inverter) == ("B1-R2-T3", "B1-R2-S2", "INV-1.2")


def test_mission_status_covers_every_module(client):
    mission = Mission.model_validate(client.get(M).json())
    assert set(mission.status) == {m.id for m in mission.modules}


def test_review_applies_decision(client):
    res = client.post("/api/findings/F-002/review", json={"decision": "rejected", "note": "x"})
    finding = Finding.model_validate(res.json())
    assert (finding.review, finding.review_note) == ("rejected", "x")
    client.post("/api/findings/F-002/review", json={"decision": "confirmed"})


def test_unknown_ids_are_404(client):
    res = client.post("/api/findings/nope/review", json={"decision": "confirmed"})
    assert res.status_code == 404
    assert client.post("/api/alerts/nope/ack").status_code == 404


def test_analyse_crop_returns_prediction(client):
    crop = open("tests/fixtures/crops/ok_10000.jpg", "rb").read()
    res = client.post("/api/analyse", files={"file": ("crop.jpg", crop, "image/jpeg")})
    assert res.status_code == 200, res.text
    Prediction.model_validate(res.json())


@pytest.mark.parametrize(
    "path",
    [
        "/api/frames/FR-B1-R2-T3-P1/thumb.png",
        "/api/findings/F-001/crop.png",
        "/api/findings/F-001/gradcam.png",
    ],
)
def test_png_endpoints(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content.startswith(PNG_MAGIC)


@pytest.mark.parametrize("path", [f"{M}/work-orders?format=csv", f"{M}/labels.csv"])
def test_csv_endpoints(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert len(res.text.strip().splitlines()) > 1


def test_report_is_html(client):
    res = client.get(f"{M}/report")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    # The Jinja2 template gets the mission's data, not a fixed mock page.
    assert "Raport de inspecție M-0001" in res.text
    assert "B1-R5-T1-M11" in res.text  # the hot cell F-012
    assert "Ordine de lucru" in res.text
    assert "Ziua 1" in res.text  # the plan


def test_eval_serves_eval_json(client, monkeypatch, tmp_path):
    from app.api.routes import eval as eval_routes

    report = eval_routes.EVAL_JSON.read_text(encoding="utf-8")  # committed by evaluate.py
    monkeypatch.setattr(eval_routes, "EVAL_JSON", tmp_path / "eval.json")
    assert client.get("/api/eval").status_code == 404
    (tmp_path / "eval.json").write_text(report, encoding="utf-8")
    res = client.get("/api/eval")
    assert res.status_code == 200
    body = EvalReport.model_validate(res.json())
    assert body.split == "test" and [m.name for m in body.models] == [
        "rules", "random_forest", "resnet18", "small_cnn"]
    assert [d.kind for d in body.degradation] == ["noise", "blur", "contrast"]
    assert all(len(d.levels) == 4 for d in body.degradation)
