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


class Crew(BaseModel):
    """A maintenance crew from config/crews.yaml."""

    id: str
    type: str
    people: list[str]
    skills: list[str]
    shift: str


class PlanTask(BaseModel):
    work_order_id: str
    crew: str  # crew id from config/crews.yaml
    people: list[str] = []
    start: str = ""  # clock time, from the crew's shift start
    end: str = ""
    start_h: float
    duration_h: float
    reason: str
    notes: list[str] = []  # the reason, one point per item


class PlanDay(BaseModel):
    day: int
    date: str
    weather: str
    capacity_h: dict[str, float]
    used_h: dict[str, float]
    off: dict[str, str] = {}  # crew id → why it does not work that day
    busy_h: dict[str, float] = {}  # crew id → hours already taken by other approved plans
    tasks: list[PlanTask]


class Plan(BaseModel):
    days: list[PlanDay]
    crews: list[Crew] = []
    unscheduled_why: dict[str, str] = {}  # work order id → why no crew could take it
    unscheduled: list[str]
    total_loss_avoided_kwh: float
    approved_at: str | None = None  # set once the engineer approves it: then it is frozen


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
