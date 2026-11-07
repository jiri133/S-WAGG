"""Greedy maintenance planner: work orders → days × crews (DESIGN_SPEC §7).

Steps: criticals first (day 1) → score order → same table/row and same crew pulled
together → each task on the earliest day it still fits → what does not fit is unscheduled.
The 5-day forecast (`config/weather.json`) closes a crew's day: electricians do not work in
the rain, cleaning does not work in wind over `cleaning_max_wind_ms`.
"""

import json
from datetime import date, timedelta

from app.schemas import Finding, Module, Plan, PlanDay, PlanTask, WorkOrder
from app.services.decision import rules, workorders


def _cfg() -> dict:
    return rules.load_rules()["planner"]


def forecast() -> list[dict]:
    """The 5-day forecast, one dict per day: sky, rain, wind_ms."""
    return json.loads((rules.CONFIG_DIR / "weather.json").read_text(encoding="utf-8"))["days"]


def closed(day: dict, crew: str) -> bool:
    """True when the weather keeps `crew` at home that day."""
    if crew == "electrical":
        return day["rain"]
    return day["wind_ms"] > _cfg()["cleaning_max_wind_ms"]


def weather_text(day: dict) -> str:
    return f"{day['sky']}, vânt {day['wind_ms']} m/s"


def travel_h(a: Module | None, b: Module) -> float:
    """Hours to walk from module a to module b; 0 at the start of the day."""
    minutes = _cfg()["travel_min"]
    if a is None or (a.block, a.row) == (b.block, b.row):
        return minutes["same_row"] / 60
    if a.block == b.block:
        return minutes["between_rows"] / 60
    return minutes["between_blocks"] / 60


def _group(
    orders: list[WorkOrder], loc: dict[str, Module]
) -> list[tuple[WorkOrder, WorkOrder | None]]:
    """Priority order, with each anchor followed by the lower tasks on its table, then its row.

    Returns (order, anchor it was pulled behind or None).
    """
    remaining, seq = list(orders), []
    while remaining:
        anchor = remaining.pop(0)
        seq.append((anchor, None))
        here = loc[anchor.module_id]
        same_table = [w for w in remaining if loc[w.module_id].table == here.table]
        same_row = [
            w
            for w in remaining
            if w not in same_table
            and (loc[w.module_id].block, loc[w.module_id].row) == (here.block, here.row)
        ]
        for w in same_table + same_row:
            remaining.remove(w)
            seq.append((w, anchor))
    return seq


def _reason(w, finding, rank, anchor, anchor_day, day, travel, loc, weather) -> str:
    if w.urgency == "critical":
        parts = ["alertă critică de siguranță: programată înaintea oricărei alte sarcini"]
    else:
        parts = [f"urgență {w.urgency}, scor {finding.score:g} (locul {rank} în prioritate)"]
    if w.ticket_status == "verify_and_repair":
        conf = round(finding.prediction.probs[finding.prediction.cls] * 100)
        parts.append(f"verifică și repară: modelul e sigur {conf}% pe {finding.prediction.cls}")
    if w.ticket_status == "reinspection":
        parts.append("reinspecție după review neconcludent")
    if anchor is not None and anchor_day == day:
        a, b = loc[anchor.module_id], loc[w.module_id]
        same_table = a.table == b.table
        where = f"aceeași masă {b.table}" if same_table else f"același rând B{b.block}-R{b.row}"
        parts.append(f"grupat cu {anchor.id} pe {where}")
    shut = [d for d in range(1, day) if closed(weather[d - 1], w.crew)]
    for d in shut:
        parts.append(f"ziua {d}: {weather_text(weather[d - 1])}, echipa {w.crew} nu lucrează")
    if day - 1 > len(shut):
        parts.append(f"nu mai încape la echipa {w.crew} în zilele de lucru de dinainte")
    if travel > 0:
        parts.append(f"deplasare {round(travel * 60)} min")
    return "; ".join(parts)


def plan(
    orders: list[WorkOrder],
    findings: list[Finding],
    modules: list[Module],
    start: date,
    weather: list[dict] | None = None,
) -> Plan:
    cfg = _cfg()
    horizon, crews = cfg["horizon_days"], cfg["capacity_h"]
    weather = weather or forecast()
    cap = {
        (d, c): 0.0 if closed(weather[d - 1], c) else h
        for d in range(1, horizon + 1)
        for c, h in crews.items()
    }
    loc = {m.id: m for m in modules}
    by_finding = {f.id: f for f in findings}
    rank = {f.id: i for i, f in enumerate(workorders.prioritised(findings), start=1)}
    ordered = sorted(orders, key=lambda w: (rank[w.finding_id], w.id))
    seq = _group([w for w in ordered if w.urgency == "critical"], loc) + _group(
        [w for w in ordered if w.urgency != "critical"], loc
    )

    used = dict.fromkeys(cap, 0.0)
    last: dict[tuple[int, str], Module] = {}
    tasks: dict[int, list[PlanTask]] = {d: [] for d in range(1, horizon + 1)}
    day_of: dict[str, int] = {}
    unscheduled, avoided = [], 0.0
    for w, anchor in seq:
        here = loc[w.module_id]
        for day in range(1, horizon + 1):
            key = (day, w.crew)
            travel = travel_h(last.get(key), here)
            if used[key] + travel + w.est_hours <= cap[key] + 1e-9:
                break
        else:
            unscheduled.append(w.id)
            continue
        f = by_finding[w.finding_id]
        anchor_day = day_of.get(anchor.id) if anchor else None
        reason = _reason(w, f, rank[f.id], anchor, anchor_day, day, travel, loc, weather)
        tasks[day].append(
            PlanTask(
                work_order_id=w.id,
                crew=w.crew,
                start_h=round(used[key] + travel, 2),
                duration_h=w.est_hours,
                reason=reason,
            )
        )
        used[key] += travel + w.est_hours
        last[key] = here
        day_of[w.id] = day
        avoided += f.loss_kwh_day * (cfg["loss_window_days"] - day + 1)

    return Plan(
        days=[
            PlanDay(
                day=d,
                date=(start + timedelta(days=d - 1)).isoformat(),
                weather=weather_text(weather[d - 1]),
                capacity_h={c: cap[(d, c)] for c in crews},
                used_h={c: round(used[(d, c)], 2) for c in crews},
                tasks=tasks[d],
            )
            for d in range(1, horizon + 1)
        ],
        unscheduled=unscheduled,
        total_loss_avoided_kwh=round(avoided, 1),
    )
