"""A mission's findings in SQLite, and the work orders and plan built from them (§7–9).

The analysis saves the findings once; reviews update them in place. Work orders and the plan
are rebuilt from the findings on every read, so a review shows up at once.
"""

import io
from datetime import timedelta

import numpy as np
from PIL import Image
from sqlmodel import Session, col, select

from app.models import FindingRow, MissionRow, PlanApprovalRow
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
    """Drop the mission's findings, and its approved plan: they belong to an old analysis."""
    for row in session.exec(select(FindingRow).where(FindingRow.mission_id == mission_id)).all():
        session.delete(row)
    if approval := session.get(PlanApprovalRow, mission_id):
        session.delete(approval)
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


def row(session: Session, finding_id: str, mission_id: str | None = None) -> FindingRow | None:
    """The finding with this id in `mission_id`, else from the most recent analysis.

    Ids repeat across missions (F-001, F-002…), so React always names the mission; without it
    a review would land on the newest mission's finding with that id.
    """
    query = select(FindingRow).where(FindingRow.id == finding_id)
    if mission_id is not None:
        query = query.where(FindingRow.mission_id == mission_id)
    return session.exec(query.order_by(col(FindingRow.pk).desc())).first()


# What the map shows for a module once the engineer decided (ModuleStatus).
REVIEWED_STATUS = {"confirmed": "finding", "rejected": "ok", "inconclusive": "unsure"}


def review(session: Session, found: FindingRow, decision: ReviewIn) -> Finding:
    """Store the decision on the finding and show it on the mission's map."""
    updated = Finding.model_validate(found.data).model_copy(
        update={"review": decision.decision, "review_note": decision.note}
    )
    found.data = updated.model_dump()
    session.add(found)
    if mission := session.get(MissionRow, found.mission_id):
        mission.status = {**mission.status, updated.module_id: REVIEWED_STATUS[decision.decision]}
        session.add(mission)
    session.commit()
    return updated


def crop(found: FindingRow) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(found.crop)).convert("L"))


def work_orders(session: Session, mission_id: str) -> list[WorkOrder]:
    rows = _rows(session, mission_id)
    created_at = rows[0].created_at if rows else ""
    found = [Finding.model_validate(r.data) for r in rows]
    return workorders.work_orders(found, park(), created_at)


def busy(session: Session, mission_id: str) -> dict[tuple[str, str], float]:
    """(ISO date, crew id) → hours the approved plans of the OTHER missions already take."""
    out: dict[tuple[str, str], float] = {}
    for row in session.exec(select(PlanApprovalRow)).all():
        if row.mission_id == mission_id:
            continue
        for day in Plan.model_validate(row.data).days:
            for crew, hours in day.used_h.items():
                out[(day.date, crew)] = out.get((day.date, crew), 0.0) + hours
    return out


def plan(session: Session, mission_id: str) -> Plan:
    """The approved plan if there is one (frozen), else a greedy plan from the work orders
    around the crew hours other approved plans already took."""
    if approval := session.get(PlanApprovalRow, mission_id):
        return Plan.model_validate(approval.data)
    orders = work_orders(session, mission_id)
    found = for_mission(session, mission_id)
    return planner.plan(orders, found, park(), PLAN_START, busy=busy(session, mission_id))


def approve(session: Session, mission_id: str, approved_at: str) -> Plan:
    """Freeze the mission's current plan; its crew hours are taken for every other mission."""
    current = plan(session, mission_id).model_copy(update={"approved_at": approved_at})
    session.merge(
        PlanApprovalRow(mission_id=mission_id, data=current.model_dump(), approved_at=approved_at)
    )
    session.commit()
    return current


def release(session: Session, mission_id: str) -> Plan:
    """Drop the approval: the crews are free again and the plan follows the reviews."""
    if approval := session.get(PlanApprovalRow, mission_id):
        session.delete(approval)
        session.commit()
    return plan(session, mission_id)
