"""Demo scenario 1 end to end (ticket 34): flight → model → findings → orders, plan, alerts, report.

The fixed seed (22) gives a critical hot cell, a sure diode, unsure findings and a reflection
seen in one pass only; every endpoint after the analysis reads the same findings.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Alert, Finding, Mission, Plan, WorkOrder
from app.services import missions, state
from app.services.decision import alerts as alerting
from tests.conftest import FAST, fly_to_end

M = "/api/missions/demo-normal"


IN_FLIGHT = {"now": 0, "max": 0}  # webhook POSTs open at the same time


@pytest.fixture(scope="module")
def client():
    async def post(url: str, payload: dict) -> None:
        IN_FLIGHT["now"] += 1
        IN_FLIGHT["max"] = max(IN_FLIGHT["max"], IN_FLIGHT["now"])
        await asyncio.sleep(0.01)
        IN_FLIGHT["now"] -= 1

    fast = missions.DEMOS["normal"].model_copy(update={"speed": FAST})  # same seed, no waiting
    with pytest.MonkeyPatch.context() as mp, TestClient(app) as c:
        mp.setitem(missions.DEMOS, "normal", fast)
        mp.setattr(alerting, "_post", post)
        assert c.post("/api/missions/demo/normal").json()["settings"]["seed"] == 22
        fly_to_end(c, "demo-normal")
        assert c.post(f"{M}/analyse").status_code == 200
        yield c
    state.drop("demo-normal")


def findings(client: TestClient) -> list[Finding]:
    return [Finding.model_validate(f) for f in client.get(f"{M}/findings").json()]


def test_findings_come_from_the_model_on_the_flown_frames(client):
    found = findings(client)
    mission = Mission.model_validate(client.get(M).json())
    assert mission.phase == "analysed" and "pending" not in mission.status.values()
    flagged = {m for m, s in mission.status.items() if s in ("finding", "unsure")}
    assert {f.module_id for f in found} == flagged
    # Calibrated model probabilities, not the fixed 0.55 / 0.93 of the old mock.
    assert all(abs(sum(f.prediction.probs.values()) - 1) < 1e-3 for f in found)
    assert {round(f.prediction.probs[f.prediction.cls], 2) for f in found} - {0.55, 0.93}
    # A predicted ok is a finding only when the safety rule trips.
    assert all(f.evidence.delta_t_k >= 20 for f in found if f.prediction.cls == "ok")
    assert all(f.evidence.frame_ids and f.evidence.pattern for f in found)


def test_scenario_1_has_the_demo_cases(client):
    found = {f.id: f for f in findings(client)}
    hot = found["F-022"]
    assert (hot.module_id, hot.prediction.cls, hot.evidence.delta_t_k) == (
        "B1-R5-T1-M11",
        "hot_cell",
        22.4,
    )
    assert hot.urgency == "critical" and hot.evidence.seen_in_both_passes
    diode = found["F-033"]
    assert (diode.prediction.cls, diode.prediction.unsure) == ("diode_substring", False)
    assert any(f.prediction.unsure for f in found.values())
    reflections = [
        f for f in found.values() if "reflexie probabilă" in (f.prediction.unsure_reason or "")
    ]
    assert reflections and all(f.urgency == "low" for f in reflections)
    raised = [Alert.model_validate(a) for a in client.get(f"{M}/alerts").json()]
    assert "AL-022" in {a.id for a in raised}
    hot_enough = {f.id for f in found.values() if f.evidence.delta_t_k >= 20}
    assert {a.finding_id for a in raised} == hot_enough


def test_orders_plan_and_report_use_the_same_findings(client):
    ids = {f.id for f in findings(client)}
    orders = [WorkOrder.model_validate(w) for w in client.get(f"{M}/work-orders").json()]
    assert {w.finding_id for w in orders} == ids  # every finding gets an order (ADR 0001)
    plan = Plan.model_validate(client.get(f"{M}/plan").json())
    planned = [t.work_order_id for d in plan.days for t in d.tasks] + plan.unscheduled
    assert sorted(planned) == sorted(w.id for w in orders)
    report = client.get(f"{M}/report").text
    assert all(f"<td>{i}</td>" in report for i in ids)
    assert "AL-022" in report and "B1-R5-T1-M11" in report


def test_rejecting_a_finding_takes_it_out_of_plan_and_report(client):
    res = client.post("/api/findings/F-033/review", json={"decision": "rejected"})
    assert res.status_code == 200
    plan = Plan.model_validate(client.get(f"{M}/plan").json())
    assert "WO-033" not in [t.work_order_id for d in plan.days for t in d.tasks]
    assert "WO-033" not in plan.unscheduled
    report = client.get(f"{M}/report").text
    assert "<td>F-033</td>" not in report and "<td>WO-033</td>" not in report


def test_score_compares_with_the_planted_truth(client):
    score = client.get(f"{M}/score").json()
    assert score["true_positive"] > 0 and score["not_inspected"] == 0


def test_webhooks_go_out_in_parallel(client):
    # One by one, ~49 deliveries kept the analysis waiting for ~14 s.
    assert IN_FLIGHT["max"] > 1
