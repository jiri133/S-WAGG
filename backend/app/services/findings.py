"""A mission's findings in SQLite, and the work orders and plan built from them (§7–9).

The analysis saves the findings once; reviews update them in place. Work orders and the plan
are rebuilt from the findings on every read, so a review shows up at once.
"""

import io
from datetime import timedelta

import numpy as np
from PIL import Image
from sqlmodel import Session, col, select

from app.models import FindingRow, MissionRow
from app.schemas import Finding, Plan, ReviewIn, WorkOrder
from app.services.decision import planner, workorders
from app.services.sim.compose import START
from app.services.sim.park import park


def _next_weekday(day):
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


PLAN_START = _next_weekday(START.date() + timedelta(days=1))  # first weekday after the flight


def png(crop: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(crop).save(buf, format="PNG")
    return buf.getvalue()


def save(
    session: Session,
    mission_id: str,
    items: list[tuple[Finding, np.ndarray | bytes]],
    created_at: str,
) -> None:
    """Replace the mission's findings; a carried finding keeps yesterday's PNG bytes."""
    clear(session, mission_id)
    for finding, crop in items:
        blob = crop if isinstance(crop, (bytes, bytearray)) else png(crop)
        session.add(
            FindingRow(
                mission_id=mission_id,
                id=finding.id,
                data=finding.model_dump(),
                crop=bytes(blob),
                created_at=created_at,
            )
        )
    session.commit()


def clear(session: Session, mission_id: str) -> None:
    for row in session.exec(select(FindingRow).where(FindingRow.mission_id == mission_id)).all():
        session.delete(row)
    session.commit()


def _rows(session: Session, mission_id: str) -> list[FindingRow]:
    query = select(FindingRow).where(FindingRow.mission_id == mission_id)
    return list(session.exec(query.order_by(col(FindingRow.pk))).all())


def for_mission(session: Session, mission_id: str) -> list[Finding]:
    return [Finding.model_validate(r.data) for r in _rows(session, mission_id)]


def previous_for(
    session: Session, mission_id: str
) -> tuple[str | None, list[tuple[Finding, bytes]]]:
    """The latest non-demo mission's findings, for the daily carry-over."""
    query = select(FindingRow).where(FindingRow.mission_id != mission_id)
    for last in session.exec(query.order_by(col(FindingRow.pk).desc())):
        mission = session.get(MissionRow, last.mission_id)
        if mission is None or mission.demo:
            continue
        rows = [(Finding.model_validate(r.data), r.crop) for r in _rows(session, last.mission_id)]
        return last.mission_id, rows
    return None, []


def merge(
    today: list[tuple[Finding, np.ndarray | bytes]],
    previous: list[tuple[Finding, bytes]],
    imaged: set[str],
    prev_id: str,
) -> list[tuple[Finding, np.ndarray | bytes]]:
    """Today's findings after carrying yesterday's open ones.

    Seen today → today's finding (the engineer's review is kept); seen ok → yesterday's finding
    is dropped; not imaged → carried with a new id and `carried_from`.
    """
    fresh = {f.module_id: (f, crop) for f, crop in today}
    old: dict[str, tuple[Finding, bytes]] = {}
    for f, crop in previous:
        old.setdefault(f.module_id, (f, crop))
    out: list[tuple[Finding, np.ndarray | bytes]] = []
    for module_id, (f, crop) in fresh.items():
        prev = old.get(module_id)
        if prev:
            pf = prev[0]
            f = f.model_copy(
                update={
                    "review": pf.review,
                    "review_note": pf.review_note,
                    "carried_from": None,
                }
            )
        out.append((f, crop))
    next_id = max((int(f.id.removeprefix("F-")) for f, _ in today), default=0) + 1
    for module_id, (f, crop) in old.items():
        if module_id in fresh or module_id in imaged:
            continue
        out.append(
            (f.model_copy(update={"id": f"F-{next_id:03d}", "carried_from": prev_id}), crop)
        )
        next_id += 1
    return out


def merge_with_previous(
    session: Session,
    mission_id: str,
    fresh: list[tuple[Finding, np.ndarray | bytes]],
    imaged: set[str],
) -> list[tuple[Finding, np.ndarray | bytes]]:
    """Carry over yesterday's findings that were not seen again today."""
    prev_id, previous = previous_for(session, mission_id)
    return merge(fresh, previous, imaged, prev_id) if previous else fresh


def row(session: Session, finding_id: str) -> FindingRow | None:
    """The finding with this id from the most recent analysis.

    The §9 routes name a finding without its mission, and ids repeat across missions.
    """
    query = select(FindingRow).where(FindingRow.id == finding_id)
    return session.exec(query.order_by(col(FindingRow.pk).desc())).first()


def review(session: Session, found: FindingRow, decision: ReviewIn) -> Finding:
    updated = Finding.model_validate(found.data).model_copy(
        update={"review": decision.decision, "review_note": decision.note}
    )
    found.data = updated.model_dump()
    session.add(found)
    session.commit()
    return updated


def crop(found: FindingRow) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(found.crop)).convert("L"))


def work_orders(session: Session, mission_id: str) -> list[WorkOrder]:
    rows = _rows(session, mission_id)
    created_at = rows[0].created_at if rows else ""
    found = [Finding.model_validate(r.data) for r in rows]
    return workorders.work_orders(found, park(), created_at)


def plan(session: Session, mission_id: str) -> Plan:
    """Greedy plan from the mission's work orders."""
    orders = work_orders(session, mission_id)
    return planner.plan(orders, for_mission(session, mission_id), park(), PLAN_START)
