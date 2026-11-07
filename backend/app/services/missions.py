"""Mission lifecycle (DESIGN_SPEC §9, §12): create, fly, re-fly, analyse.

The phase and the status of every module go to SQLite; the events and the flown frames stay in
memory (services/state.py). The frames come from the simulator (services/sim/).
"""

import asyncio
from datetime import UTC, datetime

from sqlmodel import Session, col, func, select

from app.core.db import engine
from app.models import MissionRow
from app.schemas import AgentEvent, Mission, MissionSettings
from app.schemas.stream import (
    AgentEventEvent,
    AlertRaisedEvent,
    Cloud,
    CloudEvent,
    FindingsReady,
    FindingsReadyEvent,
    FlightDone,
    FlightDoneEvent,
    FrameCapturedEvent,
    FrameCheck,
    FrameCheckedEvent,
    Waypoint,
    WaypointEvent,
)
from app.services import mock_data, state
from app.services.pipeline import check, register
from app.services.sim import artefacts, compose
from app.services.sim.park import MODULE_H_M, MODULE_W_M, TABLE_COLS, park, tables

FRAME_S = 0.35  # seconds per frame at speed 1: 80 frames and 40 tables ≈ 42 s of flight
# A re-fly goes back once the cloud has passed and the camera is fixed: no artefacts.
CLEAN = {"p_cloud": 0.0, "p_gps": 0.0, "p_glare": 0.0, "p_lost": 0.0, "inject": []}
# Fixed seeds of the §12 demo scenarios.
DEMOS: dict[str, MissionSettings] = {
    "normal": MissionSettings(seed=7, n_faults=14, p_cloud=0.05, p_gps=0.0, p_lost=0.0),
    "bad_day": MissionSettings(
        seed=11,
        p_cloud=0.25,
        p_gps=0.15,
        p_glare=0.25,
        p_lost=0.05,
        inject=["rgb", "no_panels", "low_irr", "missing"],
    ),
    "explain": MissionSettings(seed=23, p_cloud=0.0, p_gps=0.0, p_glare=0.0, p_lost=0.0),
}


def next_id(session: Session) -> str:
    n = session.exec(select(func.count()).where(col(MissionRow.id).startswith("M-"))).one()
    return f"M-{n + 1:04d}"


def create(session: Session, mission_id: str, settings: MissionSettings, demo: bool) -> MissionRow:
    row = MissionRow(
        id=mission_id,
        settings=settings.model_dump(),
        status={m.id: "pending" for m in park()},
        demo=demo,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def to_mission(row: MissionRow) -> Mission:
    settings = MissionSettings.model_validate(row.settings)
    return Mission(
        id=row.id,
        settings=settings,
        phase="flying" if state.running(row.id) else row.phase,
        modules=park(),
        status=row.status,
        truth=compose.truth(settings) if row.demo else None,
    )


def not_inspected_tables(row: MissionRow) -> list[str]:
    return [t for t, ms in tables().items() if any(row.status[m.id] == "not_inspected" for m in ms)]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def fly(mission_id: str, render: MissionSettings, table_ids: list[str]) -> None:
    """Fly over `table_ids` in flight order, sending the §9 events at the mission's speed.

    Each frame is checked as it lands. A table without any valid frame becomes not_inspected
    and a re-fly is proposed; the others are pending until the analysis.
    """
    lv, delay = state.live(mission_id), FRAME_S / render.speed
    flown = compose.frames(render)
    cloudy = {f["id"] for f in artefacts.plan(render) if f["cloud"]}
    n, ok_tables = 0, set()
    for t in table_ids:
        first = tables()[t][0]
        x, y = first.x_m + TABLE_COLS * MODULE_W_M / 2, first.y_m + MODULE_H_M
        lv.events.append(WaypointEvent(data=Waypoint(table=t, x_m=x, y_m=y)))
        await asyncio.sleep(delay)
        for raw in (f for f in flown if f.table == t):
            img = compose.frame_image(render, raw.id)
            meta = check.frame(raw, img)
            if meta.check_ok:
                meta = meta.model_copy(update={"gps_offset_detected": register.offset(img)})
            lv.frames[meta.id] = (meta, img)
            lv.events.append(FrameCapturedEvent(data=meta))
            lv.events.append(
                FrameCheckedEvent(
                    data=FrameCheck(
                        frame_id=meta.id, check_ok=meta.check_ok, problems=meta.problems
                    )
                )
            )
            if raw.id in cloudy:
                lv.events.append(CloudEvent(data=Cloud(irradiance_wm2=raw.irradiance_wm2)))
            if meta.check_ok:
                ok_tables.add(t)
            n += 1
            await asyncio.sleep(delay)

    with Session(engine) as session:
        row = session.get(MissionRow, mission_id)
        status = dict(row.status)
        for t in table_ids:
            for m in tables()[t]:
                status[m.id] = "pending" if t in ok_tables else "not_inspected"
        row.status, row.phase = status, "checked"
        session.add(row)
        session.commit()
    lv.events.append(FlightDoneEvent(data=FlightDone(frames=n)))
    for t in table_ids:
        if t not in ok_tables:
            event = AgentEvent(
                ts=_now(), kind="refly_proposed", ref=t, message=f"Re-zbor propus pentru {t}"
            )
            lv.events.append(AgentEventEvent(data=event))


def analyse(session: Session, row: MissionRow) -> None:
    """Classify every inspected module and raise the alerts.

    The findings still come from mock_data: ticket 17's pipeline is tested but not wired here
    yet, because the demo's 22 K hot cell needs the unresolved k factor (map.md, Not yet
    specified). Persisting real findings comes with tickets 20–21.
    """
    status = {m: ("ok" if s == "pending" else s) for m, s in row.status.items()}
    findings = mock_data.findings()
    for f in findings:
        if status[f.module_id] != "not_inspected":
            status[f.module_id] = "unsure" if f.prediction.unsure else "finding"
    row.status, row.phase = status, "analysed"
    session.add(row)
    session.commit()
    lv = state.live(row.id)
    lv.events.append(FindingsReadyEvent(data=FindingsReady(count=len(findings))))
    lv.events.extend(AlertRaisedEvent(data=a) for a in mock_data.alerts())
