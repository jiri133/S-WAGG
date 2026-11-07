import csv
import io
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse

from app.schemas import AgentEvent, Alert, Plan, WorkOrder
from app.services import mock_data

router = APIRouter(tags=["actions"])

CSV = {200: {"content": {"text/csv": {}}}}


def _csv(rows: list[dict], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]) if rows else [])
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
        return _csv([w.model_dump() for w in orders], f"work-orders-{mission_id}.csv")
    return orders


@router.get("/missions/{mission_id}/labels.csv", response_class=Response, responses=CSV)
def labels_csv(mission_id: str) -> Response:
    rows = [
        {
            "module_id": f.module_id,
            "predicted": f.prediction.cls,
            "review": f.review or "",
            "note": f.review_note or "",
        }
        for f in mock_data.findings()
    ]
    return _csv(rows, f"labels-{mission_id}.csv")


@router.get("/missions/{mission_id}/plan")
def get_plan(mission_id: str) -> Plan:
    return mock_data.plan()


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
