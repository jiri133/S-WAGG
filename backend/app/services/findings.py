"""A mission's findings in SQLite, and the work orders and plan built from them (§7–9).

The analysis saves the findings once; reviews update them in place. Work orders and the plan
are rebuilt from the findings on every read, so a review shows up at once.
"""

import io
from datetime import timedelta

import numpy as np
from PIL import Image
from sqlmodel import Session, col, select

from app.models import FindingRow
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
    session: Session, mission_id: str, items: list[tuple[Finding, np.ndarray]], created_at: str
) -> None:
    """Replace the mission's findings with this analysis's ones, each with its uint8 crop."""
    clear(session, mission_id)
    for finding, crop in items:
        session.add(
            FindingRow(
                mission_id=mission_id,
                id=finding.id,
                data=finding.model_dump(),
                crop=png(crop),
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
