"""Decision layer (DESIGN_SPEC §7–8): YAML rules, loss, work orders, review."""

import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Finding, Plan, Prediction, WorkOrder
from app.services.decision import loss, rules, workorders
from app.services.pipeline.infer import CLASSES
from app.services.sim.park import park
from tests import fakes
from tests.conftest import analysed_mission


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.mission = f"/api/missions/{analysed_mission(c)}"  # analysed last: reviews land here
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
    full = {c: 0.0 for c in CLASSES} | probs
    cls = max(full, key=full.get)
    return Prediction(cls=cls, probs=full, temperature=1.36, unsure=unsure)


def test_expected_risk_sits_between_ok_and_a_sure_fault():
    month = fakes.MONTH
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
    found = fakes.findings()
    once = [f.id for f in workorders.prioritised(found)]
    assert once == [f.id for f in workorders.prioritised(list(reversed(found)))]
    twins = [found[2].model_copy(update={"id": i}) for i in ("F-102", "F-101")]
    assert [f.id for f in workorders.prioritised(twins)] == ["F-101", "F-102"]
    assert once[0] == "F-001"  # the critical comes first


def _review(f: Finding, decision: str | None) -> Finding:
    return f.model_copy(update={"review": decision})


def test_unsure_finding_gets_a_verify_order_without_review():
    unsure = next(f for f in fakes.findings() if f.prediction.unsure)
    modules = park()
    [order] = workorders.work_orders([unsure], modules, "t")
    assert (order.finding_id, order.ticket_status) == (unsure.id, "verify_and_repair")
    [order] = workorders.work_orders([_review(unsure, "confirmed")], modules, "t")
    assert order.ticket_status == "pending"
    assert workorders.work_orders([_review(unsure, "rejected")], modules, "t") == []


def test_watched_finding_gets_an_order_only_once_confirmed():
    watched = fakes.findings()[0].model_copy(update={"watch": True})
    assert workorders.work_orders([watched], park(), "t") == []
    [order] = workorders.work_orders([_review(watched, "confirmed")], park(), "t")
    assert order.ticket_status == "pending"


def test_rejected_finding_gets_no_order():
    f = fakes.findings()[0]
    assert workorders.work_orders([_review(f, "rejected")], park(), "t") == []


def test_inconclusive_is_only_a_flag_and_keeps_the_order():
    for f in fakes.findings()[:4]:
        [before] = workorders.work_orders([f], park(), "t")
        [after] = workorders.work_orders([_review(f, "inconclusive")], park(), "t")
        assert after == before
        assert _review(f, "inconclusive").needs_review == f.prediction.unsure


def test_only_unsure_or_watched_findings_need_review():
    sure, unsure = fakes.findings()[0], next(f for f in fakes.findings() if f.prediction.unsure)
    assert not sure.needs_review and unsure.needs_review
    assert not _review(unsure, "confirmed").needs_review
    assert sure.model_copy(update={"watch": True}).needs_review


def test_tie_on_score_goes_to_higher_confidence():
    a, b = fakes.findings()[1:3]
    probs = {**b.prediction.probs, b.prediction.cls: 0.99}
    b = b.model_copy(
        update={"score": a.score, "prediction": b.prediction.model_copy(update={"probs": probs})}
    )
    assert [f.id for f in workorders.prioritised([a, b])] == [b.id, a.id]


# --- endpoints --------------------------------------------------------------


def test_findings_carry_decision_fields(client):
    found = [Finding.model_validate(f) for f in client.get(f"{client.mission}/findings").json()]
    assert [f.id for f in found] == [f.id for f in workorders.prioritised(found)]
    assert all(f.evidence.rule_applied.startswith("risc așteptat:") for f in found)
    hot = next(f for f in found if f.id == "F-012")  # scenario 1's hot cell, ΔT 31 K
    assert (hot.prediction.cls, hot.evidence.delta_t_k) == ("hot_cell", 31.0)
    assert (hot.urgency, hot.crew, hot.part) == ("critical", "electrical", "modul")
    assert hot.summary.startswith("ΔT 31,0 K ≥ 20 K: alertă de siguranță · hot_cell")
    assert hot.action == "Verifică celula, schimbă modulul"
    assert hot.check.startswith("Verifică celula cu camera IR") and not hot.watch
    calm = next(f for f in found if f.urgency != "critical")
    assert f"urgență {calm.urgency}" in calm.summary and "kWh/zi" in calm.summary


def _order_status(client) -> dict[str, str]:
    orders = client.get(f"{client.mission}/work-orders").json()
    return {w["finding_id"]: w["ticket_status"] for w in orders}


def test_review_rebuilds_work_orders(client):
    # F-008: unsure, the model still gives it a fair chance of being ok: watched, no order yet.
    assert "F-008" not in _order_status(client)
    mission = client.mission.removeprefix("/api/missions/")
    before = _order_status(client)
    q = f"?mission_id={mission}"
    client.post(f"/api/findings/F-008/review{q}", json={"decision": "confirmed"})
    client.post(f"/api/findings/F-012/review{q}", json={"decision": "rejected"})
    client.post(f"/api/findings/F-010/review{q}", json={"decision": "inconclusive"})
    status = _order_status(client)
    assert status["F-008"] == "pending"
    assert "F-012" not in status  # rejected: deleted, with its order
    assert "F-012" not in {f["id"] for f in client.get(f"{client.mission}/findings").json()}
    assert status["F-010"] == before["F-010"]  # inconclusive only flags it


def test_review_names_the_mission_because_finding_ids_repeat(client):
    # M-0001 and this module's mission are both scenario 1: both have an F-005.
    def review_of(mission: str) -> str | None:
        found = client.get(f"/api/missions/{mission}/findings").json()
        return next(f["review"] for f in found if f["id"] == "F-005")

    body = {"decision": "inconclusive"}
    res = client.post("/api/findings/F-005/review?mission_id=M-0001", json=body)
    assert res.status_code == 200
    assert review_of("M-0001") == "inconclusive"
    assert review_of(client.mission.removeprefix("/api/missions/")) is None  # untouched
    crop = client.get("/api/findings/F-005/crop.png?mission_id=M-0001")
    assert crop.headers["content-type"] == "image/png"
    assert client.get("/api/findings/F-005/crop.png?mission_id=nope").status_code == 404


def test_review_unknown_finding_is_404(client):
    res = client.post("/api/findings/F-999/review", json={"decision": "confirmed"})
    assert res.status_code == 404


def test_work_orders_csv_columns(client):
    res = client.get(f"{client.mission}/work-orders", params={"format": "csv"})
    assert res.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert list(rows[0]) == list(WorkOrder.model_fields)
    found = {f["id"] for f in client.get(f"{client.mission}/findings").json()}
    watched = {f["id"] for f in client.get(f"{client.mission}/findings").json() if f["watch"]}
    assert {r["finding_id"] for r in rows} == found - watched  # the rest have an order


def test_labels_csv_exports_reviews(client):
    body = {"decision": "confirmed", "note": "conector ars"}
    client.post("/api/findings/F-010/review", json=body)
    rows = list(csv.DictReader(io.StringIO(client.get(f"{client.mission}/labels.csv").text)))
    assert list(rows[0]) == ["finding_id", "module_id", "predicted", "review", "note"]
    f3 = next(r for r in rows if r["finding_id"] == "F-010")
    assert (f3["predicted"], f3["review"], f3["note"]) == (
        "module_offline",
        "confirmed",
        "conector ars",
    )


def test_review_shows_on_the_missions_map(client):
    mission = client.mission.removeprefix("/api/missions/")

    def status_of(module: str) -> str:
        return client.get(f"/api/missions/{mission}").json()["status"][module]

    f = client.get(f"{client.mission}/findings").json()[-1]
    url = f"/api/findings/{f['id']}/review?mission_id={mission}"
    steps = [("confirmed", "finding"), ("inconclusive", "unsure"), ("rejected", "ok")]
    for decision, status in steps:
        client.post(url, json={"decision": decision})
        assert status_of(f["module_id"]) == status
    assert client.post(url, json={"decision": "confirmed"}).status_code == 404  # deleted


def test_an_approved_plan_keeps_its_crews_busy_for_other_missions(client):
    own, other = client.mission, "/api/missions/M-0001"  # approve own; M-0001 is only read
    mission = own.removeprefix("/api/missions/")
    free = Plan.model_validate(client.get(f"{other}/plan").json())
    approved = Plan.model_validate(client.post(f"{own}/plan/approve").json())
    assert approved.approved_at and approved.days
    try:
        busy = Plan.model_validate(client.get(f"{other}/plan").json())
        day1 = busy.days[0]
        taken = approved.days[0].used_h
        assert day1.busy_h == {c: h for c, h in taken.items() if h > 0}
        for crew, hours in day1.busy_h.items():
            assert day1.capacity_h[crew] == pytest.approx(
                max(0, free.days[0].capacity_h[crew] - hours)
            )
        # Frozen: a review after the approval does not move its tasks.
        f = client.get(f"{own}/findings").json()[0]
        url = f"/api/findings/{f['id']}/review?mission_id={mission}"
        client.post(url, json={"decision": "rejected"})
        assert Plan.model_validate(client.get(f"{own}/plan").json()) == approved
    finally:
        released = Plan.model_validate(client.delete(f"{own}/plan/approve").json())
    assert released.approved_at is None
    assert not any(d.busy_h for d in Plan.model_validate(client.get(f"{other}/plan").json()).days)
