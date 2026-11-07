"""Decision layer (DESIGN_SPEC §7–8): YAML rules, loss, work orders, review."""

import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Finding, WorkOrder
from app.services import mock_data
from app.services.decision import loss, rules, workorders

M = "/api/missions/M-0001"


@pytest.fixture(autouse=True)
def clean_reviews():
    mock_data._reviews.clear()
    yield
    mock_data._reviews.clear()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# --- rules.py ---------------------------------------------------------------


@pytest.mark.parametrize("cls", ["hot_cell", "multi_hot", "diode_substring"])
def test_safety_rule_makes_risk_class_critical_at_20k(cls):
    d = rules.apply(cls, 20.0)
    assert (d["urgency"], d["alert"]) == ("critical", True)
    assert d["rule_applied"].startswith("decision_rules.yaml › safety:")
    assert "≥ 20 K" in d["rule_applied"]


def test_below_20k_keeps_base_urgency():
    d = rules.apply("hot_cell", 19.9)
    assert (d["urgency"], d["alert"]) == ("medium", False)
    assert d["rule_applied"].startswith("decision_rules.yaml › classes.hot_cell:")


def test_safety_rule_ignores_non_risk_classes():
    d = rules.apply("soiling", 35.0)
    assert (d["urgency"], d["alert"]) == ("low", False)


@pytest.mark.parametrize(
    ("cls", "urgency", "crew", "part", "hours"),
    [
        ("module_offline", "high", "electrical", "conectori", 0.5),
        ("diode_substring", "high", "electrical", "dioda bypass", 1.5),
        ("hot_cell", "medium", "electrical", "modul", 2.0),
        ("multi_hot", "medium", "electrical", "modul", 2.0),
        ("shadow_vegetation", "low", "cleaning", None, 0.25),
        ("soiling", "low", "cleaning", None, 0.25),
        ("other", "low", "electrical", "modul", 2.0),
    ],
)
def test_base_urgency_and_work_content(cls, urgency, crew, part, hours):
    d = rules.apply(cls, 0.0)
    assert (d["urgency"], d["crew"], d["part"], d["est_hours"]) == (urgency, crew, part, hours)
    assert "verificare:" in d["rule_applied"]


def test_score_is_weight_times_loss():
    assert rules.score("critical", 0.1) == 1.0
    assert rules.score("low", 0.1) == 0.1


# --- loss.py ----------------------------------------------------------------


def test_pvgis_yield_is_a_plausible_bucharest_year():
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    year = sum(loss.daily_yield()[m] * d for m, d in zip(range(1, 13), days, strict=True))
    assert 1200 < year < 1450


def test_loss_is_kwp_times_fraction_times_yield():
    kwh = loss.loss_kwh_day("module_offline", 11)
    assert kwh == round(0.55 * 1.00 * loss.daily_yield()[11], 3)
    assert loss.loss_kwh_day("diode_substring", 11) == round(
        0.55 * 0.33 * loss.daily_yield()[11], 3
    )
    assert loss.loss_ron_day(kwh) == round(kwh * 0.60, 2)


# --- workorders.py ----------------------------------------------------------


def _review(f: Finding, decision: str | None) -> Finding:
    return f.model_copy(update={"review": decision})


def test_unsure_finding_waits_for_confirmation():
    unsure = next(f for f in mock_data.findings() if f.prediction.unsure)
    park = mock_data.park()
    assert workorders.work_orders([unsure], park, "t") == []
    [order] = workorders.work_orders([_review(unsure, "confirmed")], park, "t")
    assert (order.finding_id, order.ticket_status) == (unsure.id, "pending")


def test_rejected_finding_gets_no_order():
    f = mock_data.findings()[0]
    assert workorders.work_orders([_review(f, "rejected")], mock_data.park(), "t") == []


def test_inconclusive_becomes_reinspection():
    f = mock_data.findings()[1]
    [order] = workorders.work_orders([_review(f, "inconclusive")], mock_data.park(), "t")
    assert (order.ticket_status, order.part, order.est_hours) == ("reinspection", None, 0.5)


def test_tie_on_score_goes_to_higher_confidence():
    a, b = mock_data.findings()[:2]
    probs = {**b.prediction.probs, b.prediction.cls: 0.99}
    b = b.model_copy(
        update={"score": a.score, "prediction": b.prediction.model_copy(update={"probs": probs})}
    )
    assert [f.id for f in workorders.prioritised([a, b])] == [b.id, a.id]


# --- endpoints --------------------------------------------------------------


def test_findings_carry_decision_fields(client):
    found = [Finding.model_validate(f) for f in client.get(f"{M}/findings").json()]
    assert [f.score for f in found] == sorted((f.score for f in found), reverse=True)
    assert all(f.evidence.rule_applied.startswith("decision_rules.yaml") for f in found)
    hot = next(f for f in found if f.id == "F-001")
    assert (hot.urgency, hot.crew, hot.part) == ("critical", "electrical", "modul")


def _order_status(client) -> dict[str, str]:
    return {w["finding_id"]: w["ticket_status"] for w in client.get(f"{M}/work-orders").json()}


def test_review_rebuilds_work_orders(client):
    assert "F-004" not in _order_status(client)  # unsure
    client.post("/api/findings/F-004/review", json={"decision": "confirmed"})
    client.post("/api/findings/F-001/review", json={"decision": "rejected"})
    client.post("/api/findings/F-002/review", json={"decision": "inconclusive"})
    status = _order_status(client)
    assert status["F-004"] == "pending"
    assert "F-001" not in status
    assert status["F-002"] == "reinspection"


def test_review_unknown_finding_is_404(client):
    res = client.post("/api/findings/F-999/review", json={"decision": "confirmed"})
    assert res.status_code == 404


def test_work_orders_csv_columns(client):
    res = client.get(f"{M}/work-orders", params={"format": "csv"})
    assert res.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert list(rows[0]) == list(WorkOrder.model_fields)
    assert {r["finding_id"] for r in rows} == {"F-001", "F-002", "F-003", "F-005"}


def test_labels_csv_exports_reviews(client):
    body = {"decision": "confirmed", "note": "conector ars"}
    client.post("/api/findings/F-003/review", json=body)
    rows = list(csv.DictReader(io.StringIO(client.get(f"{M}/labels.csv").text)))
    assert list(rows[0]) == ["finding_id", "module_id", "predicted", "review", "note"]
    f3 = next(r for r in rows if r["finding_id"] == "F-003")
    assert (f3["predicted"], f3["review"], f3["note"]) == (
        "module_offline",
        "confirmed",
        "conector ars",
    )
