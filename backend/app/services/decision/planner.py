"""Greedy maintenance planner: work orders → days × crews (DESIGN_SPEC §7).

Only weekdays are planned (crews.yaml decides which crews work). Criticals come first, then the
priority order; every order goes to the earliest day and the least-loaded crew that can do it,
so the two electricians share the work. The plan grows past five days until every order fits;
the 5-day forecast closes days, and days beyond it have no weather.

The crews come from `config/crews.yaml`: type, the parts they can change, shift, working weekdays
and days off. Electricians stop in the rain, cleaning stops in wind over
`cleaning_max_wind_ms`.
"""

import json
from datetime import date, timedelta

import yaml

from app.schemas import Crew, Finding, Module, Plan, PlanDay, PlanTask, WorkOrder
from app.services.decision import rules, workorders

WEEKDAY_RO = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]
DEFAULT_SKY = {"sky": "fără prognoză", "rain": False, "wind_ms": 0}


def _cfg() -> dict:
    return rules.load_rules()["planner"]


def forecast() -> dict:
    """The fixed demo forecast: `start` date plus one sky dict per day."""
    return json.loads((rules.CONFIG_DIR / "weather.json").read_text(encoding="utf-8"))


def sky_for(day: date, weather: dict) -> dict:
    """The forecast for `day`; days outside it are treated as good weather."""
    start = date.fromisoformat(weather["start"])
    index = (day - start).days
    return weather["days"][index] if 0 <= index < len(weather["days"]) else DEFAULT_SKY


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


def _route(ws: list[WorkOrder], loc: dict[str, Module]) -> list[WorkOrder]:
    """One crew's day: criticals first, then module by module along blocks, rows and tables."""

    def where(w: WorkOrder) -> tuple:
        m = loc[w.module_id]
        return (w.urgency != "critical", m.block, m.row, m.table, m.pos)

    return sorted(ws, key=where)


def _route_hours(ws: list[WorkOrder], loc: dict[str, Module]) -> float:
    total, prev = 0.0, None
    for w in ws:
        here = loc[w.module_id]
        total += travel_h(prev, here) + w.est_hours
        prev = here
    return total


def _reason(w, finding, rank, prev, day_no, dates, travel, loc, offs, able, crews) -> list[str]:
    if w.urgency == "critical":
        parts = ["alertă critică de siguranță: programată înaintea oricărei alte sarcini"]
    else:
        parts = [f"urgență {w.urgency}, scor {finding.score:g} (locul {rank} în prioritate)"]
    if w.ticket_status == "verify_and_repair":
        conf = round(finding.prediction.probs[finding.prediction.cls] * 100)
        parts.append(f"verifică și repară: modelul e sigur {conf}% pe {finding.prediction.cls}")
    if prev is not None:
        a, b = loc[prev.module_id], loc[w.module_id]
        if a.table == b.table:
            parts.append(f"grupat cu {prev.id} pe aceeași masă {b.table}")
        elif (a.block, a.row) == (b.block, b.row):
            parts.append(f"grupat cu {prev.id} pe același rând B{b.block}-R{b.row}")
    if len(able) < sum(c["type"] == w.crew for c in crews):
        parts.append(f"doar {', '.join(able)} schimbă „{w.part}”")
    full = 0
    for earlier in range(day_no - 1):
        d = dates[earlier]
        why = [offs[(d, c)] for c in able]
        if all(why):
            parts.append(f"ziua {earlier + 1}: " + "; ".join(dict.fromkeys(why)))
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
    text = f"{who} nu mai {verb} {w.est_hours:g} h libere în {horizon} zile lucrătoare"
    if len(able) < of_type:
        text += f"; doar {who} schimbă „{w.part}”"
    return text


def plan(
    orders: list[WorkOrder],
    findings: list[Finding],
    modules: list[Module],
    start: date,
    weather: dict | list | None = None,
    crews: list[dict] | None = None,
    busy: dict[tuple[str, str], float] | None = None,
) -> Plan:
    """Each order, in priority order, goes to the earliest day and the least-loaded capable crew
    that still has time. Only weekdays are planned, and the horizon is a cap on working days, not
    a fixed week: every order is scheduled unless the cap is not enough."""
    cfg = _cfg()
    horizon = cfg["horizon_days"]
    if isinstance(weather, list):  # tests pass just the five sky dicts
        weather = {"start": start.isoformat(), "days": weather}
    weather = weather or forecast()
    crews = crews or roster()
    by_id = {c["id"]: c for c in crews}

    dates: list[date] = []
    cursor = start
    while len(dates) < horizon:
        if cursor.weekday() < 5:  # Monday–Friday only
            dates.append(cursor)
        cursor += timedelta(days=1)
    skies = {d: sky_for(d, weather) for d in dates}
    offs = {(d, c["id"]): why_off(c, d, skies[d]) for d in dates for c in crews}
    busy = busy or {}  # (ISO date, crew id) → hours other approved plans already took
    taken = {(d, c["id"]): busy.get((d.isoformat(), c["id"]), 0.0) for d in dates for c in crews}
    cap = {
        key: 0.0 if offs[key] else max(0.0, float(by_id[key[1]]["hours"]) - taken[key])
        for key in taken
    }
    loc = {m.id: m for m in modules}
    by_finding = {f.id: f for f in findings}
    rank = {f.id: i for i, f in enumerate(workorders.prioritised(findings), start=1)}
    ordered = sorted(orders, key=lambda w: (w.urgency != "critical", rank[w.finding_id], w.id))

    assigned: dict[tuple[date, str], list[WorkOrder]] = {key: [] for key in cap}
    able_of: dict[str, list[str]] = {}
    unscheduled, unscheduled_why = [], {}
    for w in ordered:
        able_of[w.id] = able = [c["id"] for c in crews if can_do(c, w)]
        chosen = None
        for d in dates:
            options = []
            for crew_id in able:
                route = _route([*assigned[(d, crew_id)], w], loc)
                hours = _route_hours(route, loc)
                if hours <= cap[(d, crew_id)] + 1e-9:
                    options.append((hours, crew_id))
            if options:
                # earliest day; among the crews that fit, the one left with the least work
                _, crew_id = min(options, key=lambda pair: (pair[0], pair[1] == "E1"))
                chosen = (d, crew_id)
                break
        if chosen is None:
            unscheduled.append(w.id)
            of_type = sum(c["type"] == w.crew for c in crews)
            unscheduled_why[w.id] = why_unscheduled(w, able, of_type, horizon)
        else:
            assigned[chosen].append(w)

    tasks: dict[date, list[PlanTask]] = {d: [] for d in dates}
    used = dict.fromkeys(cap, 0.0)
    avoided = 0.0
    for (day, crew_id), ws in assigned.items():
        prev = None
        day_no = dates.index(day) + 1
        for w in _route(ws, loc):
            here = loc[w.module_id]
            travel = travel_h(loc[prev.module_id] if prev else None, here)
            begin = used[(day, crew_id)] + travel
            f = by_finding[w.finding_id]
            notes = _reason(w, f, rank[f.id], prev, day_no, dates, travel, loc, offs,
                            able_of[w.id], crews)
            shift = by_id[crew_id]["start"]
            tasks[day].append(
                PlanTask(
                    work_order_id=w.id,
                    crew=crew_id,
                    people=by_id[crew_id]["people"],
                    start=clock(shift, begin),
                    end=clock(shift, begin + w.est_hours),
                    start_h=round(begin, 2),
                    duration_h=w.est_hours,
                    reason="; ".join(notes),
                    notes=notes,
                )
            )
            used[(day, crew_id)] = begin + w.est_hours
            prev = w
            avoided += f.loss_kwh_day * (cfg["loss_window_days"] - day_no + 1)

    last = max((d for d in dates if tasks[d]), default=None)
    shown = [d for d in dates if last is not None and d <= last]
    return Plan(
        days=[
            PlanDay(
                day=i,
                date=d.isoformat(),
                weather=weather_text(skies[d]),
                capacity_h={c["id"]: cap[(d, c["id"])] for c in crews},
                used_h={c["id"]: round(used[(d, c["id"])], 2) for c in crews},
                off={c["id"]: why for c in crews if (why := offs[(d, c["id"])])},
                busy_h={c["id"]: round(h, 2) for c in crews if (h := taken[(d, c["id"])]) > 0},
                tasks=tasks[d],
            )
            for i, d in enumerate(shown, start=1)
        ],
        crews=[_crew_info(c) for c in crews],
        unscheduled_why=unscheduled_why,
        unscheduled=unscheduled,
        total_loss_avoided_kwh=round(avoided, 1),
    )
