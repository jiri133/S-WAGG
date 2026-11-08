"""Mock ticketing system: the default WEBHOOK_URL target (§8)."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["mock"])

_tickets: list[dict[str, Any]] = []


@router.get("/mock/ticketing")
def list_tickets(mission_id: str | None = None) -> list[dict[str, Any]]:
    """Received tickets; with a mission id, only that mission's (the mock is global)."""
    return [t for t in _tickets if mission_id is None or t.get("mission_id") == mission_id]


@router.post("/mock/ticketing")
def receive_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    """Accepts one work order or alert, as the webhook sends it."""
    _tickets.append(payload)
    return {"received": True, "count": len(_tickets)}
