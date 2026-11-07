import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.schemas import FrameMeta, Mission, MissionSettings, StreamEvent
from app.services import mock_data
from app.services.pipeline import check, register
from app.services.sim import compose

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


# Until ticket 18 stores missions, every mission flies with the default MissionSettings.
@router.get("/missions/{mission_id}/frames")
def list_frames(mission_id: str) -> list[FrameMeta]:
    """Frames delivered by the simulated flight, checked and registered (pipeline steps 1–2).

    Lost frames are absent; a frame that fails the data check keeps its problems, and the GPS
    offset is only detected on frames that passed it.
    """
    settings = MissionSettings()
    out = []
    for meta in compose.frames(settings):
        img = compose.frame_image(settings, meta.id)
        checked = check.frame(meta, img)
        if checked.check_ok:
            checked = checked.model_copy(update={"gps_offset_detected": register.offset(img)})
        out.append(checked)
    return out


@router.get("/frames/{frame_id}/thumb.png", response_class=Response, responses=PNG)
def frame_thumb(frame_id: str) -> Response:
    """The frame regenerated from the seed: gray 10–70 °C, or RGB for a wrong camera."""
    img = compose.frame_image(MissionSettings(), frame_id)
    if img is None:
        raise HTTPException(404, f"frame {frame_id} not found")
    return Response(compose.png(img), media_type="image/png")


@router.get("/missions/{mission_id}/score")
def score(mission_id: str) -> dict[str, int]:
    """Model vs. ground truth. Shape is not fixed in the spec yet (see ticket 05)."""
    n = len(mock_data.findings())
    return {"true_positive": n - 1, "false_positive": 1, "missed": 0, "not_inspected": 12}
