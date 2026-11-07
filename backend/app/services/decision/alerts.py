"""Critical alerts (DESIGN_SPEC §7–8): the safety rule, the SQLite rows and the webhook."""

import logging

import httpx
from sqlmodel import Session, select

from app.core.config import settings
from app.models import AlertRow
from app.schemas import Alert, Finding
from app.services.decision import rules

log = logging.getLogger(__name__)
ATTEMPTS = 3
TIMEOUT_S = 5.0


def raise_alerts(findings: list[Finding], raised_at: str) -> list[Alert]:
    """One critical alert per finding that trips the safety rule (risk class, ΔT ≥ 20 K)."""
    out = []
    for f in findings:
        if not rules.apply(f.prediction.cls, f.evidence.delta_t_k)["alert"]:
            continue
        delta = f"{f.evidence.delta_t_k:.1f}".replace(".", ",")
        out.append(
            Alert(
                id=f"AL-{f.id.removeprefix('F-')}",
                finding_id=f.id,
                level="critical",
                message=f"{f.prediction.cls} cu ΔT {delta} K pe {f.module_id} (≥ 20 K)",
                raised_at=raised_at,
            )
        )
    return out


def clear(session: Session, mission_id: str) -> None:
    for row in session.exec(select(AlertRow).where(AlertRow.mission_id == mission_id)).all():
        session.delete(row)
    session.commit()


def save(session: Session, mission_id: str, items: list[Alert]) -> None:
    """Replace the mission's alerts with the ones this analysis raised (Q17: results in SQLite)."""
    clear(session, mission_id)
    for alert in items:
        session.add(AlertRow(mission_id=mission_id, **alert.model_dump()))
    session.commit()


def for_mission(session: Session, mission_id: str) -> list[Alert]:
    rows = session.exec(select(AlertRow).where(AlertRow.mission_id == mission_id)).all()
    return [_alert(row) for row in sorted(rows, key=lambda row: row.id)]


def acknowledge(session: Session, alert_id: str) -> Alert | None:
    """Acknowledges every mission's alert with this id; None if it was never raised."""
    rows = session.exec(select(AlertRow).where(AlertRow.id == alert_id)).all()
    if not rows:
        return None
    for row in rows:
        row.acknowledged = True
        session.add(row)
    session.commit()
    return _alert(rows[0])


def _alert(row: AlertRow) -> Alert:
    return Alert(
        id=row.id,
        finding_id=row.finding_id,
        level=row.level,
        message=row.message,
        raised_at=row.raised_at,
        acknowledged=row.acknowledged,
    )


async def _post(url: str, payload: dict) -> None:
    """One HTTP POST; raises on a transport error or a non-2xx answer. Monkeypatched in tests."""
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        res = await client.post(url, json=payload)
        res.raise_for_status()


async def send(payload: dict, url: str | None = None) -> bool:
    """Deliver one alert or work order to WEBHOOK_URL: 3 attempts, every one logged."""
    target = url or settings.webhook_url
    ref = payload.get("id", "?")
    for attempt in range(1, ATTEMPTS + 1):
        log.info("webhook %s: attempt %s/%s → %s", ref, attempt, ATTEMPTS, target)
        try:
            await _post(target, payload)
        except httpx.HTTPError as exc:
            log.warning("webhook %s: attempt %s/%s failed: %s", ref, attempt, ATTEMPTS, exc)
        else:
            log.info("webhook %s: sent", ref)
            return True
    log.error("webhook %s: failed after %s attempts", ref, ATTEMPTS)
    return False
