"""Greedy maintenance planner: work orders → days × crews (DESIGN_SPEC §7, no weather yet).

Steps: criticals first (day 1) → score order → same table/row and same crew pulled
together → each task on the earliest day it still fits → what does not fit is unscheduled.
"""

from datetime import date, timedelta

from app.schemas import Finding, Module, Plan, PlanDay, PlanTask, WorkOrder
from app.services.decision import rules, workorders

NO_WEATHER = "fără prognoză (meteo: tichetul 28)"


def _cfg() -> dict:
    return rules.load_rules()["planner"]


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


def _reason(w, finding, rank, anchor, anchor_day, day, travel, loc) -> str:
    if w.urgency == "critical":
        parts = ["alertă critică de siguranță: programată înaintea oricărei alte sarcini"]
    else:
        parts = [f"urgență {w.urgency}, scor {finding.score:g} (locul {rank} în prioritate)"]
    if w.ticket_status == "reinspection":
        parts.append("reinspecție după review neconcludent")
    if anchor is not None and anchor_day == day:
        a, b = loc[anchor.module_id], loc[w.module_id]
        same_table = a.table == b.table
        where = f"aceeași masă {b.table}" if same_table else f"același rând B{b.block}-R{b.row}"
        parts.append(f"grupat cu {anchor.id} pe {where}")
    if day > 1:
        parts.append(f"nu mai încape la echipa {w.crew} în zilele 1–{day - 1}")
    if travel > 0:
        parts.append(f"deplasare {round(travel * 60)} min")
    return "; ".join(parts)


def plan(
    orders: list[WorkOrder], findings: list[Finding], modules: list[Module], start: date
) -> Plan:
    cfg = _cfg()
    horizon, capacity = cfg["horizon_days"], cfg["capacity_h"]
    loc = {m.id: m for m in modules}
    by_finding = {f.id: f for f in findings}
    rank = {f.id: i for i, f in enumerate(workorders.prioritised(findings), start=1)}
    ordered = sorted(orders, key=lambda w: (rank[w.finding_id], w.id))
    seq = _group([w for w in ordered if w.urgency == "critical"], loc) + _group(
        [w for w in ordered if w.urgency != "critical"], loc
    )

    used = {(d, c): 0.0 for d in range(1, horizon + 1) for c in capacity}
    last: dict[tuple[int, str], Module] = {}
    tasks: dict[int, list[PlanTask]] = {d: [] for d in range(1, horizon + 1)}
    day_of: dict[str, int] = {}
    unscheduled, avoided = [], 0.0
    for w, anchor in seq:
        here = loc[w.module_id]
        for day in range(1, horizon + 1):
            key = (day, w.crew)
            travel = travel_h(last.get(key), here)
            if used[key] + travel + w.est_hours <= capacity[w.crew] + 1e-9:
                break
        else:
            unscheduled.append(w.id)
            continue
        f = by_finding[w.finding_id]
        anchor_day = day_of.get(anchor.id) if anchor else None
        reason = _reason(w, f, rank[f.id], anchor, anchor_day, day, travel, loc)
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
                weather=NO_WEATHER,
                capacity_h=dict(capacity),
                used_h={c: round(used[(d, c)], 2) for c in capacity},
                tasks=tasks[d],
            )
            for d in range(1, horizon + 1)
        ],
        unscheduled=unscheduled,
        total_loss_avoided_kwh=round(avoided, 1),
    )
