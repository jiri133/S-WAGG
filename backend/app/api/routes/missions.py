import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

from app.schemas import FrameMeta, Mission, MissionSettings, StreamEvent
from app.services import mock_data

router = APIRouter(tags=["missions"])

PNG = {200: {"content": {"image/png": {}}}}


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"


# `model` puts StreamEvent into OpenAPI, so React gets the type generated.
SSE = {200: {"model": StreamEvent, "description": "One StreamEvent (JSON) per `data:` message"}}


@router.post("/missions")
def create_mission(settings: MissionSettings) -> Mission:
    return mock_data.mission("M-0001", settings)


@router.post("/missions/demo/{scenario}")
def create_demo_mission(scenario: str) -> Mission:
    return mock_data.mission(f"demo-{scenario}")


@router.get("/missions/{mission_id}")
def get_mission(mission_id: str) -> Mission:
    """Full state, used to resync after the SSE stream drops."""
    return mock_data.mission(mission_id)


@router.get("/missions/{mission_id}/stream", response_class=EventStreamResponse, responses=SSE)
async def stream_mission(mission_id: str) -> EventStreamResponse:
    """Server-sent events: one StreamEvent as JSON per `data:` line."""
    delay = 0.1 / mock_data.mission(mission_id).settings.speed

    async def events() -> AsyncIterator[str]:
        for ev in mock_data.stream_events():
            yield f"data: {ev.model_dump_json()}\n\n"
            await asyncio.sleep(delay)

    return EventStreamResponse(events())


@router.post("/missions/{mission_id}/fly")
def fly(mission_id: str) -> Mission:
    return mock_data.mission(mission_id).model_copy(update={"phase": "flying"})


@router.post("/missions/{mission_id}/refly")
def refly(mission_id: str) -> Mission:
    return mock_data.mission(mission_id).model_copy(update={"phase": "flying"})


@router.post("/missions/{mission_id}/analyse")
def analyse_mission(mission_id: str) -> Mission:
    return mock_data.mission(mission_id)


@router.get("/missions/{mission_id}/frames")
def list_frames(mission_id: str) -> list[FrameMeta]:
    return mock_data.frames()


@router.get("/frames/{frame_id}/thumb.png", response_class=Response, responses=PNG)
def frame_thumb(frame_id: str) -> Response:
    return Response(mock_data.gray_png(), media_type="image/png")


@router.get("/missions/{mission_id}/score")
def score(mission_id: str) -> dict[str, int]:
    """Model vs. ground truth. Shape is not fixed in the spec yet (see ticket 05)."""
    n = len(mock_data.findings())
    return {"true_positive": n - 1, "false_positive": 1, "missed": 0, "not_inspected": 12}
