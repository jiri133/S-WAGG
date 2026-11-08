"""Production derate from the latest inspection's findings.

The RL simulation's PV series is reduced by the share of the inspected park's
daily output the findings are expected to lose. The factor is relative, so the
480 × 0.55 kWp inspection park can stand in for the larger simulated farm.
"""

from __future__ import annotations

from sqlmodel import Session, col, select

from app.models import FindingRow
from app.schemas import Finding
from app.schemas.simulation import SimulationDerate
from app.services import findings as results
from app.services.decision import loss
from app.services.sim.compose import START
from app.services.sim.park import park

MONTH = START.month
"""The month used when the analysis computed each finding's ``loss_kwh_day``."""


def latest_mission(session: Session) -> str | None:
    """The mission that produced the most recent findings (highest row pk)."""
    row = session.exec(
        select(FindingRow).order_by(col(FindingRow.pk).desc()).limit(1)
    ).first()
    return row.mission_id if row is not None else None


def derate_from_findings(
    findings: list[Finding], *, mission_id: str | None = None
) -> SimulationDerate:
    """Count the findings that affect production and return the PV factor.

    Review is a gate, not a re-classification: every counted finding contributes
    its stored ``loss_kwh_day``. Rejected findings never count. Unsure or watched
    findings count only after the engineer confirms them.
    """
    counted = 0
    awaiting = 0
    rejected = 0
    lost = 0.0
    for found in findings:
        if found.review == "rejected":
            rejected += 1
            continue
        needs_confirmation = found.prediction.unsure or found.watch
        if needs_confirmation and found.review != "confirmed":
            awaiting += 1
            continue
        counted += 1
        lost += found.loss_kwh_day

    module_kwp = float(loss.load_loss()["module_kwp"])
    park_kwh_day = len(park()) * module_kwp * float(loss.daily_yield()[MONTH])
    lost = round(lost, 3)
    park_kwh_day = round(park_kwh_day, 3)
    factor = 1.0
    if park_kwh_day > 0:
        factor = max(0.0, min(1.0, 1.0 - lost / park_kwh_day))
    return SimulationDerate(
        mission_id=mission_id,
        month=MONTH,
        findings_total=len(findings),
        findings_counted=counted,
        findings_awaiting_review=awaiting,
        findings_rejected=rejected,
        lost_kwh_day=lost,
        park_kwh_day=park_kwh_day,
        factor=round(factor, 6),
    )


def current(session: Session, mission_id: str | None = None) -> SimulationDerate:
    """The derate from ``mission_id``, or from the latest mission with findings."""
    mission = mission_id or latest_mission(session)
    if mission is None:
        return derate_from_findings([])
    return derate_from_findings(
        results.for_mission(session, mission), mission_id=mission
    )
