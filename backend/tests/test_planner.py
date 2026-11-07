"""Greedy planner (DESIGN_SPEC §7): capacity, criticals on day 1, grouping, determinism."""

import random
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Plan
from app.services.decision import planner, workorders
from app.services.sim.park import park as layout
from tests import fakes

START = date(2026, 11, 8)
FAULTS = ("hot_cell", "multi_hot", "diode_substring", "module_offline", "soiling", "other")


def scenario(seed: int, n: int = 40):
    """n random findings on distinct modules; some risk classes get ΔT ≥ 20 K (critical)."""
    rng = random.Random(seed)
    modules = rng.sample(layout(), n)
    rows = []
    for m in modules:
        cls = rng.choice(FAULTS)
        hot = cls in ("hot_cell", "multi_hot", "diode_substring")
        rows.append((m.id, cls, cls, rng.choice([5.0, 10.0, 15.0, 25.0 if hot else 15.0]), False))
    findings = [fakes.finding(i, row) for i, row in enumerate(rows, start=1)]
    orders = workorders.work_orders(findings, layout(), fakes.TS)
    return orders, findings


def make_plan(seed: int, n: int = 40):
    orders, findings = scenario(seed, n)
    return planner.plan(orders, findings, layout(), START), orders


def test_same_seed_gives_the_same_multi_day_plan():
    a, _ = make_plan(7)
    b, _ = make_plan(7)
    assert a == b
    assert len([d for d in a.days if d.tasks]) >= 3
    assert [d.date for d in a.days] == [f"2026-11-{8 + i:02d}" for i in range(5)]


def test_every_order_is_planned_once_or_unscheduled():
    p, orders = make_plan(7, n=60)
    planned = [t.work_order_id for d in p.days for t in d.tasks]
    assert p.unscheduled, "60 faults should overflow 5 days × 7 h"
    assert sorted(planned + p.unscheduled) == sorted(w.id for w in orders)


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_capacity_is_respected_and_tasks_do_not_overlap(seed):
    p, _ = make_plan(seed, n=60)
    for d in p.days:
        for crew, cap in d.capacity_h.items():
            assert cap == 7.0
            tasks = [t for t in d.tasks if t.crew == crew]
            assert d.used_h[crew] <= cap
            for prev, cur in zip(tasks, tasks[1:], strict=False):
                assert cur.start_h >= prev.start_h + prev.duration_h
            if tasks:
                assert tasks[-1].start_h + tasks[-1].duration_h <= cap + 0.01


@pytest.mark.parametrize("seed", [2, 7, 9])
def test_criticals_land_on_day_1_when_they_fit(seed):
    p, orders = make_plan(seed, n=15)
    critical = {w.id for w in orders if w.urgency == "critical"}
    assert 0 < sum(w.est_hours for w in orders if w.id in critical) <= 7
    day1 = [t.work_order_id for t in p.days[0].tasks if t.crew == "electrical"]
    assert set(day1[: len(critical)]) == critical


@pytest.mark.parametrize("seed", [1, 7, 11])
def test_too_many_criticals_fill_day_1_before_anything_else(seed):
    p, orders = make_plan(seed, n=60)
    critical = {w.id for w in orders if w.urgency == "critical"}
    day1 = [t for t in p.days[0].tasks if t.crew == "electrical"]
    assert sum(w.est_hours for w in orders if w.id in critical) > 7
    assert day1[0].work_order_id in critical
    late = [t for d in p.days[1:] for t in d.tasks if t.work_order_id in critical]
    assert all("nu mai încape" in t.reason for t in late)


def test_every_task_has_a_reason():
    p, _ = make_plan(7)
    reasons = [t.reason for d in p.days for t in d.tasks]
    assert reasons and all(r.strip() for r in reasons)
    assert any("grupat cu" in r for r in reasons)
    assert any("nu mai încape" in r for r in reasons)


def test_grouped_tasks_share_the_anchor_row():
    p, orders = make_plan(7)
    loc = {m.id: m for m in layout()}
    row = {w.id: (loc[w.module_id].block, loc[w.module_id].row) for w in orders}
    grouped = [t for d in p.days for t in d.tasks if "grupat cu" in t.reason]
    assert grouped
    for t in grouped:
        anchor = t.reason.split("grupat cu ")[1].split(" ")[0]
        assert row[anchor] == row[t.work_order_id]


def test_travel_times_follow_the_spec():
    park = {m.id: m for m in layout()}
    a = park["B1-R1-T1-M01"]
    assert planner.travel_h(None, a) == 0
    assert planner.travel_h(a, park["B1-R1-T4-M12"]) == 0
    assert planner.travel_h(a, park["B1-R2-T1-M01"]) == pytest.approx(10 / 60)
    assert planner.travel_h(a, park["B2-R1-T1-M01"]) == pytest.approx(20 / 60)


def test_plan_endpoint_serves_the_missions_plan():
    with TestClient(app) as c:
        r = c.get("/api/missions/M-0001/plan")
        orders = c.get("/api/missions/M-0001/work-orders").json()
    assert r.status_code == 200
    p = Plan.model_validate(r.json())
    planned = [t.work_order_id for d in p.days for t in d.tasks]
    assert sorted(planned + p.unscheduled) == sorted(w["id"] for w in orders)
    critical = {w["id"] for w in orders if w["urgency"] == "critical"}
    first = p.days[0].tasks[0]
    assert first.work_order_id in critical and p.days[0].date == "2026-11-08"
    assert first.reason.startswith("alertă critică")
    assert p.total_loss_avoided_kwh > 0


def test_unsure_order_is_planned_as_verify_and_repair():
    p = planner.plan(fakes.work_orders(), fakes.findings(), layout(), START)
    [task] = [t for d in p.days for t in d.tasks if t.work_order_id == "WO-004"]
    assert "verifică și repară: modelul e sigur 55% pe multi_hot" in task.reason
