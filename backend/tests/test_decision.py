"""Decision layer (DESIGN_SPEC §7–8): YAML rules, loss, work orders, review."""

import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Finding, Prediction, WorkOrder
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


@pytest.mark.parametrize("cls", ["hot_cell", "multi_hot", "diode_substring", "soiling", "ok"])
def test_safety_rule_trips_at_20k_whatever_the_class(cls):
    d = rules.apply(cls, 20.0)
    assert (d["urgency"], d["alert"], d["crew"]) == ("critical", True, "electrical")
    assert d["rule"].startswith("decision_rules.yaml › safety:")
    assert "≥ 20 K" in d["rule"]


def test_below_20k_keeps_base_urgency():
    d = rules.apply("hot_cell", 19.9)
    assert (d["urgency"], d["alert"]) == ("medium", False)
    assert d["rule"] == "urgență din hot_cell (decision_rules.yaml › classes.hot_cell: medium)"


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
    assert d["check"]


def test_weight_follows_the_base_urgency():
    assert (rules.weight("diode_substring"), rules.weight("hot_cell"), rules.weight("ok")) == (
        5,
        2,
        1,
    )


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


def _pred(probs: dict[str, float], unsure: bool = False) -> Prediction:
    full = {c: 0.0 for c in mock_data.CLASSES} | probs
    cls = max(full, key=full.get)
    return Prediction(cls=cls, probs=full, temperature=1.36, unsure=unsure)


def test_expected_risk_sits_between_ok_and_a_sure_fault():
    month = mock_data.MOCK_MONTH
    sure = workorders.finding_fields(_pred({"diode_substring": 1.0}), 5.0, month)
    mixed = workorders.finding_fields(_pred({"ok": 0.6, "diode_substring": 0.4}), 5.0, month)
    healthy = workorders.finding_fields(_pred({"ok": 1.0}), 5.0, month)
    assert sure["score"] == round(5 * loss.loss_kwh_day("diode_substring", month), 3)
    assert healthy["score"] == 0
    assert 0 < mixed["score"] < sure["score"]
    assert mixed["score"] == pytest.approx(0.4 * sure["score"], abs=1e-3)
    assert mixed["loss_kwh_day"] == pytest.approx(0.4 * sure["loss_kwh_day"], abs=1e-3)


def test_urgency_comes_from_the_largest_contribution():
    # argmax is hot_cell (medium), but 0.3 × 5 × offline loss outweighs 0.7 × 2 × hot_cell loss
    f = workorders.finding_fields(_pred({"hot_cell": 0.7, "module_offline": 0.3}), 5.0, 11)
    assert f["urgency"] == "high"
    assert (f["crew"], f["part"]) == ("electrical", "modul")  # work content: model's class
    assert f["rule_applied"].startswith("risc așteptat: 0,30 module_offline × pondere 5")
    assert "urgență din module_offline" in f["rule_applied"]


def test_safety_makes_critical_even_when_the_model_is_sure_of_ok():
    f = workorders.finding_fields(_pred({"ok": 0.99, "hot_cell": 0.01}), 22.0, 11)
    assert (f["urgency"], f["crew"]) == ("critical", "electrical")
    assert "safety: ΔT 22,0 K ≥ 20 K" in f["rule_applied"]


def test_priority_order_is_stable():
    found = mock_data.findings()
    once = [f.id for f in workorders.prioritised(found)]
    assert once == [f.id for f in workorders.prioritised(list(reversed(found)))]
    twins = [found[2].model_copy(update={"id": i}) for i in ("F-102", "F-101")]
    assert [f.id for f in workorders.prioritised(twins)] == ["F-101", "F-102"]
    assert once[0] == "F-001"  # the critical comes first


def _review(f: Finding, decision: str | None) -> Finding:
    return f.model_copy(update={"review": decision})


def test_unsure_finding_gets_a_verify_order_without_review():
    unsure = next(f for f in mock_data.findings() if f.prediction.unsure)
    park = mock_data.park()
    [order] = workorders.work_orders([unsure], park, "t")
    assert (order.finding_id, order.ticket_status) == (unsure.id, "verify_and_repair")
    [order] = workorders.work_orders([_review(unsure, "confirmed")], park, "t")
    assert order.ticket_status == "pending"
    assert workorders.work_orders([_review(unsure, "rejected")], park, "t") == []


def test_rejected_finding_gets_no_order():
    f = mock_data.findings()[0]
    assert workorders.work_orders([_review(f, "rejected")], mock_data.park(), "t") == []


def test_inconclusive_becomes_reinspection():
    f = mock_data.findings()[1]
    [order] = workorders.work_orders([_review(f, "inconclusive")], mock_data.park(), "t")
    assert (order.ticket_status, order.part, order.est_hours) == ("reinspection", None, 0.5)


def test_tie_on_score_goes_to_higher_confidence():
    a, b = mock_data.findings()[1:3]
    probs = {**b.prediction.probs, b.prediction.cls: 0.99}
    b = b.model_copy(
        update={"score": a.score, "prediction": b.prediction.model_copy(update={"probs": probs})}
    )
    assert [f.id for f in workorders.prioritised([a, b])] == [b.id, a.id]


# --- endpoints --------------------------------------------------------------


def test_findings_carry_decision_fields(client):
    found = [Finding.model_validate(f) for f in client.get(f"{M}/findings").json()]
    assert [f.id for f in found] == [f.id for f in workorders.prioritised(found)]
    assert all(f.evidence.rule_applied.startswith("risc așteptat:") for f in found)
    hot = next(f for f in found if f.id == "F-001")
    assert (hot.urgency, hot.crew, hot.part) == ("critical", "electrical", "modul")


def _order_status(client) -> dict[str, str]:
    return {w["finding_id"]: w["ticket_status"] for w in client.get(f"{M}/work-orders").json()}


def test_review_rebuilds_work_orders(client):
    assert _order_status(client)["F-004"] == "verify_and_repair"  # unsure
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
    assert {r["finding_id"] for r in rows} == {"F-001", "F-002", "F-003", "F-004", "F-005"}


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
