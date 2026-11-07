"""Server-sent events of a mission (DESIGN_SPEC §9)."""

from typing import Literal

from pydantic import BaseModel

StreamEventType = Literal[
    "waypoint",
    "frame_captured",
    "frame_checked",
    "cloud",
    "flight_done",
    "findings_ready",
    "alert_raised",
    "agent_event",
]


class StreamEvent(BaseModel):
    type: StreamEventType
    data: dict
