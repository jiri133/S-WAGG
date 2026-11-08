"""Greedy maintenance planner: work orders → days × crews (DESIGN_SPEC §7).

Steps: criticals first (day 1) → score order → each order on the earliest day a crew that
can do it still has the time → each crew's day walked along tables and rows → what does not
fit in the horizon is unscheduled.

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


def no_forecast(day: int) -> dict:
    """A day past the forecast: unknown weather, so it keeps no crew at home."""
    return {"day": day, "sky": "fără prognoză", "rain": False, "wind_ms": None}


def closed(day: dict, crew: str) -> bool:
    """True when the weather keeps `crew` at home that day."""
    if crew == "electrical":
        return day["rain"]
    return (day["wind_ms"] or 0) > _cfg()["cleaning_max_wind_ms"]


def weather_text(day: dict) -> str:
    if day["wind_ms"] is None:
        return day["sky"]
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


def _reason(w, finding, rank, prev, day, travel, loc, offs, able, crews) -> list[str]:
    if w.urgency == "critical":
        parts = ["alertă critică de siguranță: programată înaintea oricărei alte sarcini"]
    else:
        parts = [f"urgență {w.urgency}, scor {finding.score:g} (locul {rank} în prioritate)"]
    if w.ticket_status == "verify_and_repair":
        conf = round(finding.prediction.probs[finding.prediction.cls] * 100)
        parts.append(f"verifică și repară: modelul e sigur {conf}% pe {finding.prediction.cls}")
    if w.ticket_status == "reinspection":
        parts.append("reinspecție după review neconcludent")
    if prev is not None:
        a, b = loc[prev.module_id], loc[w.module_id]
        if a.table == b.table:
            parts.append(f"grupat cu {prev.id} pe aceeași masă {b.table}")
        elif (a.block, a.row) == (b.block, b.row):
            parts.append(f"grupat cu {prev.id} pe același rând B{b.block}-R{b.row}")
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


def why_unscheduled(w: WorkOrder, able: list[str], longest: float, max_days: int) -> str:
    if not able:
        return f"nicio echipă nu schimbă „{w.part}”"
    who = ", ".join(able)
    if w.est_hours > longest:
        return f"durează {w.est_hours:g} h, mai mult decât o tură a echipei {who}"
    return f"{who} nu are {w.est_hours:g} h libere în {max_days} de zile"


def plan(
    orders: list[WorkOrder],
    findings: list[Finding],
    modules: list[Module],
    start: date,
    weather: list[dict] | None = None,
    crews: list[dict] | None = None,
) -> Plan:
    """Each order, in priority order, goes to the earliest day a crew that can do it still has
    the time; a lower order never takes the place of a higher one. The plan has as many days as
    the orders need (at least `horizon_days`, at most `max_days`). Then every crew's day is
    walked module by module (same table, then same row), criticals first."""
    cfg = _cfg()
    weather, crews = weather or forecast(), crews or roster()
    by_id = {c["id"]: c for c in crews}
    dates: dict[int, date] = {}
    skies: dict[int, dict] = {}
    offs: dict[tuple[int, str], str | None] = {}
    cap: dict[tuple[int, str], float] = {}
    assigned: dict[tuple[int, str], list[WorkOrder]] = {}

    def open_day(d: int) -> None:
        if d in dates:
            return
        dates[d] = start + timedelta(days=d - 1)
        skies[d] = weather[d - 1] if d <= len(weather) else no_forecast(d)
        for c in crews:
            key = (d, c["id"])
            offs[key] = why_off(c, dates[d], skies[d])
            cap[key] = 0.0 if offs[key] else float(c["hours"])
            assigned[key] = []

    for d in range(1, cfg["horizon_days"] + 1):
        open_day(d)
    loc = {m.id: m for m in modules}
    by_finding = {f.id: f for f in findings}
    rank = {f.id: i for i, f in enumerate(workorders.prioritised(findings), start=1)}
    ordered = sorted(orders, key=lambda w: (w.urgency != "critical", rank[w.finding_id], w.id))

    able_of: dict[str, list[str]] = {}
    unscheduled, unscheduled_why = [], {}
    for w in ordered:
        able_of[w.id] = able = [c["id"] for c in crews if can_do(c, w)]
        longest = max((float(by_id[c]["hours"]) for c in able), default=0.0)
        key = None
        for d in range(1, cfg["max_days"] + 1) if w.est_hours <= longest else ():
            open_day(d)
            key = next(
                (
                    (d, c)
                    for c in able
                    if _route_hours(_route([*assigned[(d, c)], w], loc), loc)
                    <= cap[(d, c)] + 1e-9
                ),
                None,
            )
            if key:
                break
        if key is None:
            unscheduled.append(w.id)
            unscheduled_why[w.id] = why_unscheduled(w, able, longest, cfg["max_days"])
        else:
            assigned[key].append(w)

    last = max((d for (d, _), ws in assigned.items() if ws), default=0)
    days = range(1, max(cfg["horizon_days"], last) + 1)
    tasks: dict[int, list[PlanTask]] = {d: [] for d in days}
    used = dict.fromkeys(cap, 0.0)
    avoided = 0.0
    for (day, crew_id), ws in assigned.items():
        prev = None
        for w in _route(ws, loc):
            here = loc[w.module_id]
            travel = travel_h(loc[prev.module_id] if prev else None, here)
            begin = used[(day, crew_id)] + travel
            f = by_finding[w.finding_id]
            notes = _reason(w, f, rank[f.id], prev, day, travel, loc, offs, able_of[w.id], crews)
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
            avoided += f.loss_kwh_day * max(0, cfg["loss_window_days"] - day + 1)

    return Plan(
        days=[
            PlanDay(
                day=d,
                date=dates[d].isoformat(),
                weather=weather_text(skies[d]),
                capacity_h={c["id"]: cap[(d, c["id"])] for c in crews},
                used_h={c["id"]: round(used[(d, c["id"])], 2) for c in crews},
                off={c["id"]: why for c in crews if (why := offs[(d, c["id"])])},
                tasks=tasks[d],
            )
            for d in days
        ],
        crews=[_crew_info(c) for c in crews],
        unscheduled_why=unscheduled_why,
        unscheduled=unscheduled,
        total_loss_avoided_kwh=round(avoided, 1),
    )
