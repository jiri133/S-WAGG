"""Greedy maintenance planner: work orders → days × crews (DESIGN_SPEC §7).

Steps: criticals first (day 1) → score order → same table/row and same crew type pulled
together → each task on the earliest day a crew that can do it still has time → what does
not fit is unscheduled.

The crews come from `config/crews.yaml`: type, people, the parts they can change, shift,
working weekdays and days off. The 5-day forecast (`config/weather.json`) closes a day too:
electricians do not work in the rain, cleaning does not work in wind over
`cleaning_max_wind_ms`.
"""

import json
from datetime import date, timedelta

import yaml

from app.schemas import Crew, Finding, Module, Plan, PlanDay, PlanTask, WorkOrder
from app.services.decision import rules, workorders

WEEKDAY_RO = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]


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


def roster() -> list[dict]:
    """The maintenance crews from `config/crews.yaml`."""
    text = (rules.CONFIG_DIR / "crews.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)["crews"]


def can_do(crew: dict, w: WorkOrder) -> bool:
    """Right crew type, and the part (if any) is one the crew can change."""
    return crew["type"] == w.crew and (w.part is None or w.part in crew["skills"])


def why_off(crew: dict, on: date, sky: dict) -> str | None:
    """Why `crew` does not work on `on`, or None if it works."""
    if closed(sky, crew["type"]):
        return f"{weather_text(sky)}, echipa {crew['type']} nu lucrează"
    if on.strftime("%a") not in crew["weekdays"]:
        return f"{crew['id']} nu lucrează {WEEKDAY_RO[on.weekday()]}"
    if on.isoformat() in crew["days_off"]:
        return f"{crew['id']} e în concediu"
    return None


def clock(start: str, hours: float) -> str:
    """'08:00' + 1.5 h → '09:30'."""
    h, m = map(int, start.split(":"))
    total = h * 60 + m + round(hours * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


SHORT_RO = {"Mon": "L", "Tue": "Ma", "Wed": "Mi", "Thu": "J", "Fri": "V", "Sat": "S", "Sun": "D"}


def _crew_info(c: dict) -> Crew:
    days = " ".join(SHORT_RO[d] for d in c["weekdays"])
    shift = f"{c['start']}–{clock(c['start'], c['hours'])}, {days}"
    return Crew(id=c["id"], type=c["type"], people=c["people"], skills=c["skills"], shift=shift)


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


def _reason(w, finding, rank, anchor, anchor_day, day, travel, loc, offs, able, crews) -> list[str]:
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
    if len(able) < sum(c["type"] == w.crew for c in crews):
        parts.append(f"doar {', '.join(able)} schimbă „{w.part}”")
    full = 0
    for d in range(1, day):
        why = [offs[(d, c)] for c in able]
        if all(why):
            parts.append(f"ziua {d}: " + "; ".join(dict.fromkeys(why)))
        else:
            full += 1
    if full:
        parts.append(f"nu mai încape la {', '.join(able)} în zilele de lucru de dinainte")
    if travel > 0:
        parts.append(f"deplasare {round(travel * 60)} min")
    return parts


def why_unscheduled(w: WorkOrder, able: list[str], of_type: int, horizon: int) -> str:
    if not able:
        return f"nicio echipă nu schimbă „{w.part}”"
    who, verb = ", ".join(able), "are" if len(able) == 1 else "au"
    text = f"{who} nu mai {verb} {w.est_hours:g} h libere în {horizon} zile"
    if len(able) < of_type:
        text += f"; doar {who} schimbă „{w.part}”"
    return text


def _first_slot(able, here, hours, horizon, used, cap, last):
    """(day, crew id, travel h) of the earliest day a crew in `able` still has the time."""
    for day in range(1, horizon + 1):
        for c in able:
            travel = travel_h(last.get((day, c)), here)
            if used[(day, c)] + travel + hours <= cap[(day, c)] + 1e-9:
                return day, c, travel
    return None


def plan(
    orders: list[WorkOrder],
    findings: list[Finding],
    modules: list[Module],
    start: date,
    weather: list[dict] | None = None,
    crews: list[dict] | None = None,
) -> Plan:
    cfg = _cfg()
    horizon = cfg["horizon_days"]
    weather, crews = weather or forecast(), crews or roster()
    by_id = {c["id"]: c for c in crews}
    dates = {d: start + timedelta(days=d - 1) for d in range(1, horizon + 1)}
    offs = {(d, c["id"]): why_off(c, dates[d], weather[d - 1]) for d in dates for c in crews}
    cap = {key: 0.0 if why else float(by_id[key[1]]["hours"]) for key, why in offs.items()}
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
    unscheduled, avoided, unscheduled_why = [], 0.0, {}
    for w, anchor in seq:
        here = loc[w.module_id]
        able = [c["id"] for c in crews if can_do(c, w)]
        slot = _first_slot(able, here, w.est_hours, horizon, used, cap, last)
        if slot is None:
            unscheduled.append(w.id)
            of_type = sum(c["type"] == w.crew for c in crews)
            unscheduled_why[w.id] = why_unscheduled(w, able, of_type, horizon)
            continue
        day, crew_id, travel = slot
        key = (day, crew_id)
        f = by_finding[w.finding_id]
        anchor_day = day_of.get(anchor.id) if anchor else None
        notes = _reason(w, f, rank[f.id], anchor, anchor_day, day, travel, loc, offs, able, crews)
        begin = used[key] + travel
        tasks[day].append(
            PlanTask(
                work_order_id=w.id,
                crew=crew_id,
                people=by_id[crew_id]["people"],
                start=clock(by_id[crew_id]["start"], begin),
                end=clock(by_id[crew_id]["start"], begin + w.est_hours),
                start_h=round(begin, 2),
                duration_h=w.est_hours,
                reason="; ".join(notes),
                notes=notes,
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
                capacity_h={c["id"]: cap[(d, c["id"])] for c in crews},
                used_h={c["id"]: round(used[(d, c["id"])], 2) for c in crews},
                off={c["id"]: why for c in crews if (why := offs[(d, c["id"])])},
                tasks=tasks[d],
            )
            for d in range(1, horizon + 1)
        ],
        crews=[_crew_info(c) for c in crews],
        unscheduled_why=unscheduled_why,
        unscheduled=unscheduled,
        total_loss_avoided_kwh=round(avoided, 1),
    )
