"""The mission report: HTML from a Jinja2 template (DESIGN_SPEC §8), served by FastAPI."""

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlmodel import Session

from app.services import findings as results
from app.services.decision import alerts as alerting
from app.services.decision import workorders
from app.services.report import llm
from app.services.sim.compose import START

WEEKDAYS_RO = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]
MONTHS_RO = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie",
             "august", "septembrie", "octombrie", "noiembrie", "decembrie"]


def _ro_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WEEKDAYS_RO[d.weekday()]}, {d.day} {MONTHS_RO[d.month - 1]} {d.year}"


_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(["html"]),
)
_env.filters["ro_date"] = _ro_date


def render(mission_id: str, session: Session) -> str:
    """One HTML page with the mission's findings, work orders, plan and alerts.

    A finding the engineer rejected is left out, like its work order.
    """
    found = results.for_mission(session, mission_id)
    findings = workorders.prioritised([f for f in found if f.review != "rejected"])
    orders = results.work_orders(session, mission_id)
    plan = results.plan(session, mission_id)
    alerts = alerting.for_mission(session, mission_id)
    return _env.get_template("report.html.j2").render(
        mission_id=mission_id,
        findings=findings,
        orders=orders,
        orders_by_id={w.id: w for w in orders},
        inspected_at=f"{START.day} {MONTHS_RO[START.month - 1]} {START.year}, {START:%H:%M}",
        plan=plan,
        alerts=alerts,
        summary=llm.summarise(llm.facts(mission_id, findings, orders, plan, alerts)),
    )
