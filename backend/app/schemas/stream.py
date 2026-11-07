"""Server-sent events of a mission (DESIGN_SPEC §9).

Each message is `{"type": ..., "data": ...}`; `type` picks the payload model of `data`, so React
gets one typed union generated from OpenAPI.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from app.schemas.actions import AgentEvent, Alert
from app.schemas.mission import FrameMeta


class Waypoint(BaseModel):
    """The drone reaches a table: centre of the table, metres from the park's top-left corner."""

    table: str
    x_m: float
    y_m: float


class FrameCheck(BaseModel):
    frame_id: str
    check_ok: bool
    problems: list[str]


class Cloud(BaseModel):
    """The frame just captured was taken under a cloud."""

    irradiance_wm2: float


class FlightDone(BaseModel):
    frames: int  # frames delivered by this flight


class FindingsReady(BaseModel):
    count: int


class WaypointEvent(BaseModel):
    type: Literal["waypoint"] = "waypoint"
    data: Waypoint


class FrameCapturedEvent(BaseModel):
    type: Literal["frame_captured"] = "frame_captured"
    data: FrameMeta


class FrameCheckedEvent(BaseModel):
    type: Literal["frame_checked"] = "frame_checked"
    data: FrameCheck


class CloudEvent(BaseModel):
    type: Literal["cloud"] = "cloud"
    data: Cloud


class FlightDoneEvent(BaseModel):
    type: Literal["flight_done"] = "flight_done"
    data: FlightDone


class FindingsReadyEvent(BaseModel):
    type: Literal["findings_ready"] = "findings_ready"
    data: FindingsReady


class AlertRaisedEvent(BaseModel):
    type: Literal["alert_raised"] = "alert_raised"
    data: Alert


class AgentEventEvent(BaseModel):
    type: Literal["agent_event"] = "agent_event"
    data: AgentEvent


AnyEvent = (
    WaypointEvent
    | FrameCapturedEvent
    | FrameCheckedEvent
    | CloudEvent
    | FlightDoneEvent
    | FindingsReadyEvent
    | AlertRaisedEvent
    | AgentEventEvent
)


class StreamEvent(RootModel[Annotated[AnyEvent, Field(discriminator="type")]]):
    """One SSE message."""
