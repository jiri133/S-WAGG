"""Mock ticketing system: the default WEBHOOK_URL target (§8)."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["mock"])

_tickets: list[dict[str, Any]] = []


@router.get("/mock/ticketing")
def list_tickets() -> list[dict[str, Any]]:
    return _tickets


@router.post("/mock/ticketing")
def receive_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    """Accepts one work order or alert, as the webhook sends it."""
    _tickets.append(payload)
    return {"received": True, "count": len(_tickets)}
