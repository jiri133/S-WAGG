"""The mission report: HTML from a Jinja2 template (DESIGN_SPEC §8), served by FastAPI."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlmodel import Session

from app.services import findings as results
from app.services.decision import alerts as alerting
from app.services.decision import workorders

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(["html"]),
)


def render(mission_id: str, session: Session) -> str:
    """One HTML page with the mission's findings, work orders, plan and alerts.

    A finding the engineer rejected is left out, like its work order.
    """
    found = results.for_mission(session, mission_id)
    return _env.get_template("report.html.j2").render(
        mission_id=mission_id,
        findings=workorders.prioritised([f for f in found if f.review != "rejected"]),
        orders=results.work_orders(session, mission_id),
        plan=results.plan(session, mission_id),
        alerts=alerting.for_mission(session, mission_id),
    )
