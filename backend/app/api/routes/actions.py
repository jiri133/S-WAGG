import csv
import io
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse

from app.schemas import AgentEvent, Alert, Plan, WorkOrder
from app.services import mock_data
from app.services.decision import planner

router = APIRouter(tags=["actions"])

CSV = {200: {"content": {"text/csv": {}}}}


def _csv(rows: list[dict], fieldnames: list[str], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(buf.getvalue(), media_type="text/csv", headers=headers)


@router.get(
    "/missions/{mission_id}/work-orders",
    response_model=list[WorkOrder],
    responses=CSV,
)
def list_work_orders(mission_id: str, format: Literal["json", "csv"] = "json"):
    orders = mock_data.work_orders()
    if format == "csv":
        rows = [w.model_dump() for w in orders]
        return _csv(rows, list(WorkOrder.model_fields), f"work-orders-{mission_id}.csv")
    return orders


LABEL_FIELDS = ["finding_id", "module_id", "predicted", "review", "note"]


@router.get("/missions/{mission_id}/labels.csv", response_class=Response, responses=CSV)
def labels_csv(mission_id: str) -> Response:
    """The engineer's labels per finding (empty review = not reviewed yet)."""
    rows = [
        {
            "finding_id": f.id,
            "module_id": f.module_id,
            "predicted": f.prediction.cls,
            "review": f.review or "",
            "note": f.review_note or "",
        }
        for f in mock_data.findings()
    ]
    return _csv(rows, LABEL_FIELDS, f"labels-{mission_id}.csv")


@router.get("/missions/{mission_id}/plan")
def get_plan(mission_id: str) -> Plan:
    """Greedy plan from today's work orders, starting the day after the mission."""
    start = date.fromisoformat(mock_data.MOCK_TS[:10]) + timedelta(days=1)
    return planner.plan(mock_data.work_orders(), mock_data.findings(), mock_data.park(), start)


@router.get("/missions/{mission_id}/alerts")
def list_alerts(mission_id: str) -> list[Alert]:
    return mock_data.alerts()


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str) -> Alert:
    for a in mock_data.alerts():
        if a.id == alert_id:
            return a.model_copy(update={"acknowledged": True})
    raise HTTPException(404, f"alert {alert_id} not found")


@router.get("/missions/{mission_id}/events")
def list_events(mission_id: str) -> list[AgentEvent]:
    return mock_data.events()


@router.get("/missions/{mission_id}/report", response_class=HTMLResponse)
def report(mission_id: str) -> HTMLResponse:
    return HTMLResponse(mock_data.report_html(mission_id))
