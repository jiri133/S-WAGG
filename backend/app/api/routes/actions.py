import csv
import io
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse

from app.api.deps import SessionDep
from app.schemas import AgentEvent, Alert, Plan, WorkOrder
from app.services import findings as results
from app.services import report as reports
from app.services import state
from app.services.decision import alerts

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
def list_work_orders(
    mission_id: str, session: SessionDep, format: Literal["json", "csv"] = "json"
):
    orders = results.work_orders(session, mission_id)
    if format == "csv":
        rows = [w.model_dump() for w in orders]
        return _csv(rows, list(WorkOrder.model_fields), f"work-orders-{mission_id}.csv")
    return orders


LABEL_FIELDS = ["finding_id", "module_id", "predicted", "review", "note"]


@router.get("/missions/{mission_id}/labels.csv", response_class=Response, responses=CSV)
def labels_csv(mission_id: str, session: SessionDep) -> Response:
    """The engineer's labels per finding (empty review = not reviewed yet)."""
    rows = [
        {
            "finding_id": f.id,
            "module_id": f.module_id,
            "predicted": f.prediction.cls,
            "review": f.review or "",
            "note": f.review_note or "",
        }
        for f in results.for_mission(session, mission_id)
    ]
    return _csv(rows, LABEL_FIELDS, f"labels-{mission_id}.csv")


@router.get("/missions/{mission_id}/plan")
def get_plan(mission_id: str, session: SessionDep) -> Plan:
    """Greedy plan from the mission's work orders, starting the day after the flight."""
    return results.plan(session, mission_id)


@router.get("/missions/{mission_id}/alerts")
def list_alerts(mission_id: str, session: SessionDep) -> list[Alert]:
    """The alerts this mission's analysis raised."""
    return alerts.for_mission(session, mission_id)


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str, session: SessionDep) -> Alert:
    if acked := alerts.acknowledge(session, alert_id):
        return acked
    raise HTTPException(404, f"Alerta {alert_id} nu există")


@router.get("/missions/{mission_id}/events")
def list_events(mission_id: str) -> list[AgentEvent]:
    """The mission's agent journal (§8), in the order the agent wrote it."""
    return state.live(mission_id).journal


@router.get("/missions/{mission_id}/report", response_class=HTMLResponse)
def report(mission_id: str, session: SessionDep) -> HTMLResponse:
    """The report the React iframe shows: findings, work orders, plan and alerts (§8)."""
    return HTMLResponse(reports.render(mission_id, session))
