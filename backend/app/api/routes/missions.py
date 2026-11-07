from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.api.deps import SessionDep
from app.models import MissionRow
from app.schemas import FrameMeta, Mission, MissionSettings, StreamEvent
from app.services import missions, mock_data, state
from app.services.pipeline import check, register
from app.services.sim import compose
from app.services.sim.park import tables

router = APIRouter(tags=["missions"])

PNG = {200: {"content": {"image/png": {}}}}


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"


# `model` puts StreamEvent into OpenAPI, so React gets the type generated.
SSE = {200: {"model": StreamEvent, "description": "One StreamEvent (JSON) per `data:` message"}}


def _row(session: Session, mission_id: str) -> MissionRow:
    row = session.get(MissionRow, mission_id)
    if row is None:
        raise HTTPException(404, f"mission {mission_id} not found")
    return row


def _idle(row: MissionRow, *phases: str) -> None:
    if state.running(row.id):
        raise HTTPException(409, f"mission {row.id} is flying")
    if row.phase not in phases:
        raise HTTPException(409, f"mission {row.id} is {row.phase}, needs {' or '.join(phases)}")


@router.post("/missions")
def create_mission(settings: MissionSettings, session: SessionDep) -> Mission:
    row = missions.create(session, missions.next_id(session), settings, demo=False)
    return missions.to_mission(row)


@router.post("/missions/demo/{scenario}")
def create_demo_mission(
    scenario: Literal["normal", "bad_day", "explain"], session: SessionDep
) -> Mission:
    """(Re)creates `demo-{scenario}` from its fixed seed; an earlier run is dropped."""
    mission_id = f"demo-{scenario}"
    state.drop(mission_id)
    if old := session.get(MissionRow, mission_id):
        session.delete(old)
        session.commit()
    return missions.to_mission(
        missions.create(session, mission_id, missions.DEMOS[scenario], demo=True)
    )


@router.get("/missions/{mission_id}")
def get_mission(mission_id: str, session: SessionDep) -> Mission:
    """Full state, used to resync after the SSE stream drops."""
    return missions.to_mission(_row(session, mission_id))


@router.get("/missions/{mission_id}/stream", response_class=EventStreamResponse, responses=SSE)
async def stream_mission(
    mission_id: str,
    session: SessionDep,
    last_event_id: Annotated[int | None, Header()] = None,
) -> EventStreamResponse:
    """Server-sent events: one StreamEvent as JSON per `data:` line, numbered by `id:`.

    Replays the events after `Last-Event-ID`, then follows the mission until it is idle again.
    """
    _row(session, mission_id)
    return EventStreamResponse(state.sse(mission_id, last_event_id))


@router.post("/missions/{mission_id}/fly")
async def fly(mission_id: str, session: SessionDep) -> Mission:
    """Starts the flight over every table; progress arrives on the stream."""
    row = _row(session, mission_id)
    _idle(row, "planned")
    settings = MissionSettings.model_validate(row.settings)
    state.start(mission_id, missions.fly(mission_id, settings, list(tables())))
    return missions.to_mission(row)


@router.post("/missions/{mission_id}/refly")
async def refly(mission_id: str, session: SessionDep) -> Mission:
    """Flies again over the not_inspected tables, without artefacts; they go back to pending."""
    row = _row(session, mission_id)
    _idle(row, "checked", "analysed", "reviewed")
    redo = missions.not_inspected_tables(row)
    if not redo:
        raise HTTPException(409, f"mission {mission_id} has no table to re-fly")
    clean = MissionSettings.model_validate(row.settings).model_copy(update=missions.CLEAN)
    state.start(mission_id, missions.fly(mission_id, clean, redo))
    return missions.to_mission(row)


@router.post("/missions/{mission_id}/analyse")
async def analyse_mission(mission_id: str, session: SessionDep) -> Mission:
    # async on purpose: the analysis sends its events in one go, between two stream polls.
    row = _row(session, mission_id)
    _idle(row, "checked")
    missions.analyse(session, row)
    return missions.to_mission(row)


@router.get("/missions/{mission_id}/frames")
def list_frames(mission_id: str, session: SessionDep) -> list[FrameMeta]:
    """Frames delivered by the flight so far, checked and registered (pipeline steps 1–2).

    Lost frames are absent. A frame that fails the data check keeps its problems, and the GPS
    offset is only detected on frames that passed it. After a restart the memory is empty, so
    the frames are regenerated from the seed and checked again.
    """
    row = _row(session, mission_id)
    if flown := state.live(mission_id).frames:
        return [meta for meta, _ in flown.values()]
    if row.phase == "planned":
        return []
    settings = MissionSettings.model_validate(row.settings)
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
    """The flown frame (gray 10–70 °C, or RGB for a wrong camera); else regenerated from the
    default seed."""
    img = state.frame_image(frame_id)
    if img is None:
        img = compose.frame_image(MissionSettings(), frame_id)
    if img is None:
        raise HTTPException(404, f"frame {frame_id} not found")
    return Response(compose.png(img), media_type="image/png")


@router.get("/missions/{mission_id}/score")
def score(mission_id: str) -> dict[str, int]:
    """Model vs. ground truth. Shape is not fixed in the spec yet (see ticket 05)."""
    n = len(mock_data.findings())
    return {"true_positive": n - 1, "false_positive": 1, "missed": 0, "not_inspected": 12}
