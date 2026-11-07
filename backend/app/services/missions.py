"""Mission lifecycle (DESIGN_SPEC §9, §12): create, fly, re-fly, analyse.

The phase and the status of every module go to SQLite; the events and the flown frames stay in
memory (services/state.py). The frames come from the simulator (services/sim/).
"""

import asyncio
from datetime import UTC, datetime

import numpy as np
from fastapi.datastructures import State
from sqlmodel import Session, col, func, select

from app.core.db import engine
from app.models import MissionRow
from app.schemas import AgentEvent, FrameMeta, Mission, MissionSettings
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
from app.services import findings as results
from app.services import state
from app.services.decision import alerts, workorders
from app.services.pipeline import analyse as pipeline
from app.services.pipeline import check, register
from app.services.sim import artefacts, compose
from app.services.sim.compose import START
from app.services.sim.park import MODULE_H_M, MODULE_W_M, TABLE_COLS, park, tables

FRAME_S = 0.35  # seconds per frame at speed 1: 80 frames and 40 tables ≈ 42 s of flight
# A re-fly goes back once the cloud has passed and the camera is fixed: no artefacts.
CLEAN = {"p_cloud": 0.0, "p_gps": 0.0, "p_glare": 0.0, "p_lost": 0.0, "inject": []}
# Fixed seeds of the §12 demo scenarios.
DEMOS: dict[str, MissionSettings] = {
    "normal": MissionSettings(seed=22, n_faults=14, p_cloud=0.05, p_gps=0.0, p_lost=0.0),
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
    alerts.clear(session, mission_id)  # a re-created demo starts without its old results
    results.clear(session, mission_id)
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


def _journal(lv: state.Live, kind: str, ref: str, message: str) -> None:
    """One line in the mission's agent journal, streamed to the timeline too."""
    event = AgentEvent(ts=_now(), kind=kind, ref=ref, message=message)
    lv.journal.append(event)
    lv.events.append(AgentEventEvent(data=event))


async def _deliver(lv: state.Live, ref: str, payload: dict) -> None:
    """POST one alert or work order to the webhook and journal the outcome."""
    if await alerts.send(payload):
        _journal(lv, "webhook_sent", ref, f"Webhook trimis pentru {ref}")
    else:
        _journal(
            lv,
            "webhook_failed",
            ref,
            f"Webhook eșuat după {alerts.ATTEMPTS} încercări pentru {ref}",
        )


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
            if not meta.check_ok:
                rejected = "; ".join(meta.problems)
                _journal(lv, "frame_rejected", meta.id, f"Cadru respins: {rejected}")
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
            _journal(lv, "refly_proposed", t, f"Re-zbor propus pentru {t}")


def flown_frames(row: MissionRow) -> list[tuple[FrameMeta, np.ndarray]]:
    """The mission's checked and registered frames: the flown ones, else regenerated.

    After a restart the memory is empty, so the frames come back from the seed and are checked
    again (a re-fly done before the restart is lost with them).
    """
    if flown := state.live(row.id).frames:
        return list(flown.values())
    if row.phase == "planned":
        return []
    settings = MissionSettings.model_validate(row.settings)
    out = []
    for meta in compose.frames(settings):
        img = compose.frame_image(settings, meta.id)
        checked = check.frame(meta, img)
        if checked.check_ok:
            checked = checked.model_copy(update={"gps_offset_detected": register.offset(img)})
        out.append((checked, img))
    return out


async def analyse(session: Session, row: MissionRow, app_state: State) -> None:
    """Classify every inspected module, save the findings, raise the alerts, send the orders.

    A pending module with no image in any valid pass becomes not_inspected.
    """
    s = app_state  # the model runs in a thread, so open streams keep going
    found, imaged = await asyncio.to_thread(
        pipeline.findings, flown_frames(row), s.model, s.temperature, s.thresholds, START.month
    )
    status = dict(row.status)
    for m, s in status.items():
        if s == "pending":
            status[m] = "ok" if m in imaged else "not_inspected"
    for f, _ in found:
        status[f.module_id] = "unsure" if f.prediction.unsure else "finding"
    row.status, row.phase = status, "analysed"
    session.add(row)
    session.commit()

    lv, raised_at = state.live(row.id), _now()
    findings = [f for f, _ in found]
    results.save(session, row.id, found, raised_at)
    lv.events.append(FindingsReadyEvent(data=FindingsReady(count=len(findings))))

    raised = alerts.raise_alerts(findings, raised_at)
    alerts.save(session, row.id, raised)
    for alert in raised:
        lv.events.append(AlertRaisedEvent(data=alert))
        _journal(lv, "alert_raised", alert.id, f"Alertă critică: {alert.message}")
        await _deliver(lv, alert.id, alert.model_dump())

    for order in workorders.work_orders(findings, park(), raised_at):
        created = f"Ordin de lucru {order.id} pentru {order.module_id}"
        _journal(lv, "work_order_created", order.id, created)
        await _deliver(lv, order.id, order.model_dump())
