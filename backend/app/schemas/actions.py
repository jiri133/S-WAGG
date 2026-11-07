"""Work orders, plan, alerts and the agent log (DESIGN_SPEC §8–9)."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.park import FaultClass, Urgency


class WorkOrder(BaseModel):
    id: str
    finding_id: str
    module_id: str
    string: str
    inverter: str
    fault: FaultClass
    part: str | None
    crew: str
    est_hours: float
    urgency: Urgency
    evidence_url: str
    created_at: str
    ticket_status: str


class PlanTask(BaseModel):
    work_order_id: str
    crew: str
    start_h: float
    duration_h: float
    reason: str


class PlanDay(BaseModel):
    day: int
    date: str
    weather: str
    capacity_h: dict[str, float]
    used_h: dict[str, float]
    tasks: list[PlanTask]


class Plan(BaseModel):
    days: list[PlanDay]
    unscheduled: list[str]
    total_loss_avoided_kwh: float


class Alert(BaseModel):
    id: str
    finding_id: str
    level: Literal["critical"]
    message: str
    raised_at: str
    acknowledged: bool = False


class AgentEvent(BaseModel):
    ts: str
    kind: str
    message: str
    ref: str | None = None
