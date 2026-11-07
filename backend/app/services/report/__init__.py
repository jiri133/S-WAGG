"""The mission report: HTML from a Jinja2 template (DESIGN_SPEC §8), served by FastAPI."""

from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlmodel import Session

from app.services import mock_data
from app.services.decision import alerts as alerting
from app.services.decision import planner

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(["html"]),
)


def render(mission_id: str, session: Session) -> str:
    """One HTML page with the findings, work orders, plan and alerts of the mission."""
    findings = mock_data.findings()
    orders = mock_data.work_orders()
    start = date.fromisoformat(mock_data.MOCK_TS[:10]) + timedelta(days=1)
    return _env.get_template("report.html.j2").render(
        mission_id=mission_id,
        findings=findings,
        orders=orders,
        plan=planner.plan(orders, findings, mock_data.park(), start),
        alerts=alerting.for_mission(session, mission_id),
    )
