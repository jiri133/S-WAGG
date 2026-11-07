"""Optional LLM summary of the report (Q13): facts-only JSON in, template fallback on any doubt."""

import json
import logging
import re

import httpx

from app.core.config import settings
from app.schemas import Alert, Finding, Plan, WorkOrder

log = logging.getLogger(__name__)

TIMEOUT_S = 5.0
MAX_TOKENS = 300
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-opus-5-5"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o-mini"
SYSTEM = (
    "Ești asistentul unui raport de inspecție termică a unui parc fotovoltaic. "
    "Scrie un rezumat scurt (cel mult trei propoziții), în română, folosind doar faptele și "
    "cifrele din JSON-ul primit. Nu inventa numere și nu adăuga date care lipsesc."
)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def facts(
    mission_id: str,
    findings: list[Finding],
    orders: list[WorkOrder],
    plan: Plan,
    alerts: list[Alert],
) -> dict:
    """Only what the report shows: no crops, probabilities or other internal data."""
    return {
        "mission_id": mission_id,
        "finding_count": len(findings),
        "findings": [
            {
                "id": f.id,
                "module_id": f.module_id,
                "class": f.prediction.cls,
                "urgency": f.urgency,
                "delta_t_k": f.evidence.delta_t_k,
            }
            for f in findings
        ],
        "work_order_count": len(orders),
        "work_orders": [
            {
                "id": w.id,
                "module_id": w.module_id,
                "fault": w.fault,
                "crew": w.crew,
                "est_hours": w.est_hours,
                "urgency": w.urgency,
            }
            for w in orders
        ],
        "plan_days": [
            {
                "day": day.day,
                "date": day.date,
                "weather": day.weather,
                "tasks": [
                    {
                        "work_order_id": task.work_order_id,
                        "crew": task.crew,
                        "duration_h": task.duration_h,
                    }
                    for task in day.tasks
                ],
            }
            for day in plan.days
        ],
        "unscheduled": plan.unscheduled,
        "total_loss_avoided_kwh": plan.total_loss_avoided_kwh,
        "alert_count": len(alerts),
        "alerts": [{"id": a.id, "message": a.message} for a in alerts],
    }


def _post(url: str, body: dict, headers: dict) -> dict:
    response = httpx.post(url, json=body, headers=headers, timeout=TIMEOUT_S)
    response.raise_for_status()
    return response.json()


def _anthropic(key: str, prompt: str) -> str:
    body = _post(
        ANTHROPIC_URL,
        {
            "model": ANTHROPIC_MODEL,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        },
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    if body.get("stop_reason") == "refusal":
        return ""
    return "".join(block["text"] for block in body["content"] if block["type"] == "text")


def _openai(key: str, prompt: str) -> str:
    body = _post(
        OPENAI_URL,
        {
            "model": OPENAI_MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
        },
        {"Authorization": f"Bearer {key}"},
    )
    return body["choices"][0]["message"]["content"]


def _only_known_numbers(text: str, sent: str) -> bool:
    """Q13: every number in the summary must already appear in the JSON we sent."""
    known = {match.group().replace(",", ".") for match in NUMBER.finditer(sent)}
    return all(match.group().replace(",", ".") in known for match in NUMBER.finditer(text))


def summarise(payload: dict) -> str | None:
    """A validated Romanian summary, or None so the Jinja2 template stays the report (Q13)."""
    if not settings.report_llm:
        return None
    prompt = json.dumps(payload, ensure_ascii=False)
    try:
        if settings.anthropic_api_key:
            text = _anthropic(settings.anthropic_api_key, prompt)
        elif settings.openai_api_key:
            text = _openai(settings.openai_api_key, prompt)
        else:
            return None
    except Exception:  # any LLM failure falls back to the template, never breaks the report
        log.warning("report LLM summary failed; falling back to the template", exc_info=True)
        return None
    text = text.strip()
    return text if text and _only_known_numbers(text, prompt) else None
