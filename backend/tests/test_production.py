"""Inspection derate rules (production.py)."""

import pytest
from sqlmodel import Session

from app.core.db import engine
from app.models import FindingRow
from app.services import findings as results
from app.services import production
from app.services.decision import loss
from app.services.sim.park import park


@pytest.fixture
def session():
    with Session(engine) as session:
        yield session


def base_finding(session: Session):
    findings = results.for_mission(session, "M-0001")
    assert findings, "the session fixture must analyse M-0001"
    return findings[0]


def variant(found, *, unsure=False, watch=False, review=None, kwh=1.0):
    return found.model_copy(
        update={
            "prediction": found.prediction.model_copy(update={"unsure": unsure}),
            "watch": watch,
            "review": review,
            "loss_kwh_day": kwh,
        }
    )


def park_potential() -> float:
    module_kwp = float(loss.load_loss()["module_kwp"])
    return round(
        len(park()) * module_kwp * float(loss.daily_yield()[production.MONTH]), 3
    )


def test_sure_finding_counts_automatically(session):
    found = base_finding(session)
    derate = production.derate_from_findings([variant(found, kwh=5.0)])

    assert derate.findings_total == 1
    assert derate.findings_counted == 1
    assert derate.findings_awaiting_review == 0
    assert derate.lost_kwh_day == 5.0
    assert derate.park_kwh_day == park_potential()
    assert derate.factor == round(max(0.0, 1.0 - 5.0 / park_potential()), 6)


def test_unsure_finding_waits_for_confirmation(session):
    found = base_finding(session)
    unsure = variant(found, unsure=True, kwh=5.0)

    waiting = production.derate_from_findings([unsure])
    assert waiting.findings_counted == 0
    assert waiting.findings_awaiting_review == 1
    assert waiting.factor == 1.0

    confirmed = production.derate_from_findings(
        [unsure.model_copy(update={"review": "confirmed"})]
    )
    assert confirmed.findings_counted == 1
    assert confirmed.lost_kwh_day == 5.0
    assert confirmed.factor < 1.0


def test_watched_finding_waits_for_confirmation(session):
    found = base_finding(session)
    watched = variant(found, unsure=False, watch=True, kwh=5.0)

    waiting = production.derate_from_findings([watched])
    assert waiting.findings_counted == 0
    assert waiting.findings_awaiting_review == 1

    confirmed = production.derate_from_findings(
        [watched.model_copy(update={"review": "confirmed"})]
    )
    assert confirmed.findings_counted == 1


def test_rejected_finding_never_counts(session):
    found = base_finding(session)
    derate = production.derate_from_findings(
        [variant(found, unsure=True, review="rejected", kwh=5.0)]
    )

    assert derate.findings_rejected == 1
    assert derate.findings_counted == 0
    assert derate.findings_awaiting_review == 0
    assert derate.factor == 1.0


def test_counts_partition_the_findings(session):
    found = base_finding(session)
    findings = [
        variant(found, kwh=1.0),
        variant(found, unsure=True, kwh=2.0),
        variant(found, unsure=True, review="confirmed", kwh=3.0),
        variant(found, review="rejected", kwh=4.0),
    ]

    derate = production.derate_from_findings(findings)

    assert derate.findings_total == 4
    assert derate.findings_counted == 2
    assert derate.findings_awaiting_review == 1
    assert derate.findings_rejected == 1
    assert derate.lost_kwh_day == 4.0


def test_no_findings_means_no_derate():
    derate = production.derate_from_findings([])

    assert derate.mission_id is None
    assert derate.findings_total == 0
    assert derate.lost_kwh_day == 0.0
    assert derate.factor == 1.0


def test_latest_mission_uses_the_most_recent_findings(session):
    row = FindingRow(
        mission_id="M-TEST",
        id="F-999",
        data=base_finding(session).model_dump(),
        crop=b"",
        created_at="2026-11-07T10:00:00Z",
    )
    session.add(row)
    session.commit()
    try:
        assert production.latest_mission(session) == "M-TEST"
    finally:
        session.delete(row)
        session.commit()


def test_current_returns_a_valid_derate(session):
    derate = production.current(session)

    assert derate.mission_id is not None
    assert 0.0 <= derate.factor <= 1.0
    assert derate.park_kwh_day > 0
