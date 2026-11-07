"""Findings → priorities and work orders, after the engineer's review (DESIGN_SPEC §7–8)."""

from app.schemas import Finding, Module, Prediction, WorkOrder
from app.services.decision import loss, rules


def finding_fields(prediction: Prediction, delta_t_k: float, month: int) -> dict:
    """Prediction + ΔT → the Finding fields owned by the decision layer.

    `rule_applied` belongs in `Finding.evidence`; the rest are top-level Finding fields.
    """
    decision = rules.apply(prediction.cls, delta_t_k)
    kwh = loss.loss_kwh_day(prediction.cls, month)
    return {
        "urgency": decision["urgency"],
        "loss_kwh_day": kwh,
        "loss_ron_day": loss.loss_ron_day(kwh),
        "score": rules.score(decision["urgency"], kwh),
        "crew": decision["crew"],
        "part": decision["part"],
        "est_hours": decision["est_hours"],
        "rule_applied": decision["rule_applied"],
    }


def prioritised(findings: list[Finding]) -> list[Finding]:
    """Highest score first; on a tie the more confident prediction wins."""
    return sorted(
        findings,
        key=lambda f: (f.score, f.prediction.probs[f.prediction.cls]),
        reverse=True,
    )


def work_orders(findings: list[Finding], modules: list[Module], created_at: str) -> list[WorkOrder]:
    """Rejected → no order. Unsure → none until reviewed. Inconclusive → reinspection."""
    by_id = {m.id: m for m in modules}
    reinspection = rules.load_rules()["reinspection"]
    orders = []
    for f in prioritised(findings):
        if f.review == "rejected" or (f.prediction.unsure and f.review is None):
            continue
        module = by_id[f.module_id]
        order = WorkOrder(
            id=f"WO-{f.id.removeprefix('F-')}",
            finding_id=f.id,
            module_id=f.module_id,
            string=module.string,
            inverter=module.inverter,
            fault=f.prediction.cls,
            part=f.part,
            crew=f.crew,
            est_hours=f.est_hours,
            urgency=f.urgency,
            evidence_url=f.evidence.crop_url,
            created_at=created_at,
            ticket_status="pending",
        )
        if f.review == "inconclusive":
            order = order.model_copy(update={**reinspection, "ticket_status": "reinspection"})
        orders.append(order)
    return orders
