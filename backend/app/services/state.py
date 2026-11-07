"""Ephemeral mission state (decision Q17): the events sent so far, the running flight and the
flown frames live in memory. A restart loses them; SQLite keeps the phase and the results.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Coroutine
from dataclasses import dataclass, field

import numpy as np

from app.schemas import AgentEvent, FrameMeta
from app.schemas.stream import AnyEvent

log = logging.getLogger(__name__)
POLL_S = 0.05  # how often an open stream looks for new events
RETRY_MS = 1000  # EventSource reconnect delay


@dataclass
class Live:
    events: list[AnyEvent] = field(default_factory=list)  # index = SSE event id
    frames: dict[str, tuple[FrameMeta, np.ndarray]] = field(default_factory=dict)
    journal: list[AgentEvent] = field(default_factory=list)  # GET /missions/{id}/events
    job: asyncio.Task | None = None


_live: dict[str, Live] = {}


def live(mission_id: str) -> Live:
    return _live.setdefault(mission_id, Live())


def running(mission_id: str) -> bool:
    job = _live[mission_id].job if mission_id in _live else None
    return job is not None and not job.done()


def start(mission_id: str, coro: Coroutine) -> None:
    """Run a flight in the background; its events reach every open stream."""
    task = asyncio.create_task(coro)
    task.add_done_callback(_log_failure)
    live(mission_id).job = task


def _log_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception():
        log.error("mission job failed", exc_info=task.exception())


def drop(mission_id: str) -> None:
    """Forget a mission's progress and stop its flight."""
    gone = _live.pop(mission_id, None)
    if gone and gone.job:
        gone.job.cancel()


def clear() -> None:
    """What a restart does to memory."""
    for mission_id in list(_live):
        drop(mission_id)


def frame_image(frame_id: str) -> np.ndarray | None:
    """The image of a flown frame, from the most recently started mission that has it.

    Frame ids repeat across missions (they name the table and pass), so this is a best guess.
    """
    for lv in reversed(_live.values()):
        if frame_id in lv.frames:
            return lv.frames[frame_id][1]
    return None


async def sse(mission_id: str, last_event_id: int | None) -> AsyncIterator[str]:
    """Events after `last_event_id` (all if None), then new ones as they come.

    The stream closes once it has sent something and no flight is running, so a stream opened
    while the mission is idle waits for the next action. EventSource reconnects by itself and
    sends `Last-Event-ID`, so nothing is sent twice. An id past the end comes from before a
    restart, when the numbering started again: then everything is sent.
    """
    lv = live(mission_id)
    i = 0 if last_event_id is None or last_event_id >= len(lv.events) else last_event_id + 1
    sent = False
    yield f"retry: {RETRY_MS}\n\n"
    while True:
        while i < len(lv.events):
            yield f"id: {i}\ndata: {lv.events[i].model_dump_json()}\n\n"
            i += 1
            sent = True
        if sent and not running(mission_id) and i == len(lv.events):
            return
        await asyncio.sleep(POLL_S)
