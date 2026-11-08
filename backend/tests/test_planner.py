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


# One crew of each type, every day, 7 h, every part: the planner's rules without the roster.
ONE = [
    {"id": t, "type": t, "people": [t], "skills": ["modul", "dioda bypass", "conectori"],
     "start": "08:00", "hours": 7, "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
     "days_off": []}
    for t in ("electrical", "cleaning")
]


def make_plan(seed: int, n: int = 40):
    orders, findings = scenario(seed, n)
    return planner.plan(orders, findings, layout(), START, crews=ONE), orders


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
            assert cap in (0.0, 7.0)  # 0 when the weather keeps the crew home
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


CLEAR = [{"day": d, "sky": "senin", "rain": False, "wind_ms": 3} for d in range(1, 6)]


def test_no_electrical_work_in_the_rain_and_no_cleaning_in_strong_wind():
    orders, findings = scenario(7, n=60)
    p = planner.plan(orders, findings, layout(), START, crews=ONE)  # day 2 rain, day 3 wind
    rain, wind = p.days[1], p.days[2]
    assert rain.weather.startswith("ploaie") and rain.capacity_h["electrical"] == 0
    assert not [t for t in rain.tasks if t.crew == "electrical"]
    assert wind.capacity_h["cleaning"] == 0
    assert not [t for t in wind.tasks if t.crew == "cleaning"]
    later = [t for d in p.days[2:] for t in d.tasks if t.crew == "electrical"]
    rained_out = "ziua 2: ploaie, vânt 6 m/s, echipa electrical nu lucrează"
    assert any(rained_out in t.reason for t in later)


def test_clear_week_keeps_full_capacity_every_day():
    orders, findings = scenario(7, n=60)
    p = planner.plan(orders, findings, layout(), START, weather=CLEAR, crews=ONE)
    assert all(d.capacity_h == {"electrical": 7.0, "cleaning": 7.0} for d in p.days)
    assert all("nu lucrează" not in t.reason for d in p.days for t in d.tasks)


def roster_plan():
    orders, findings = scenario(7, n=60)
    return planner.plan(orders, findings, layout(), START), orders  # config/crews.yaml


def test_crews_work_only_on_their_days_and_shifts():
    p, _ = roster_plan()
    sunday, thursday = p.days[0], p.days[3]  # 2026-11-08 is a Sunday
    assert sunday.off["E2"] == "E2 nu lucrează duminică" and sunday.capacity_h["E2"] == 0
    assert not [t for t in sunday.tasks if t.crew in ("E2", "C1")]
    assert thursday.off["E2"] == "E2 e în concediu"  # days_off: 2026-11-11 in crews.yaml
    first = next(t for t in sunday.tasks if t.crew == "E1")
    assert first.start == "08:00" and first.people == ["Electrician 1", "Electrician 2"]
    assert {c.id: c.shift for c in p.crews}["E2"] == "07:00–15:00, L Ma Mi J V"


def test_module_swaps_go_only_to_crews_that_can_change_modules():
    p, orders = roster_plan()
    part = {w.id: w.part for w in orders}
    tasks = [t for d in p.days for t in d.tasks]
    assert {t.crew for t in tasks if part[t.work_order_id] == "modul"} == {"E1"}
    assert any(t.crew == "E2" for t in tasks)  # E2 still takes diodes and connectors
    assert any("doar E1 schimbă „modul”" in t.reason for t in tasks)


def test_clock_adds_hours_to_the_shift_start():
    assert planner.clock("07:00", 1.5) == "08:30"
    assert planner.clock("08:00", 0.25) == "08:15"


def test_unscheduled_orders_say_why_and_tasks_have_their_reason_as_points():
    p, orders = roster_plan()
    assert p.unscheduled and set(p.unscheduled_why) == set(p.unscheduled)
    part = {w.id: w.part for w in orders}
    for wid in p.unscheduled:
        if part[wid] == "modul":
            why = "E1 nu mai are 2 h libere în 5 zile; doar E1 schimbă „modul”"
            assert p.unscheduled_why[wid] == why
    task = p.days[0].tasks[0]
    assert task.notes and task.reason == "; ".join(task.notes)
    assert (task.start, task.end) == ("08:00", planner.clock("08:00", task.duration_h))


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_a_lower_order_never_takes_the_place_of_a_higher_one(seed):
    orders, findings = scenario(seed, n=60)
    p = planner.plan(orders, findings, layout(), START)  # config/crews.yaml, skills included
    rank = {f.id: i for i, f in enumerate(workorders.prioritised(findings))}
    by_id = {w.id: w for w in orders}
    planned = [by_id[t.work_order_id] for d in p.days for t in d.tasks]
    for wid in p.unscheduled:
        left = by_id[wid]
        same_work = [w for w in planned if (w.crew, w.part) == (left.crew, left.part)]
        assert all(rank[w.finding_id] < rank[left.finding_id] for w in same_work)
