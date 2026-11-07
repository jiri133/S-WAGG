"""Findings → expected-risk priorities and work orders for every finding (DESIGN_SPEC §7–8)."""

from app.schemas import Finding, Module, Prediction, WorkOrder
from app.services.decision import loss, rules

SHOWN_TERMS = 3


def _num(x: float, digits: int) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def contributions(probs: dict[str, float], month: int) -> dict[str, float]:
    """Class → p(c) × base urgency weight(c) × loss kWh/day(c); ok contributes 0."""
    return {c: p * rules.weight(c) * loss.loss_kwh_day(c, month) for c, p in probs.items()}


def _risk_text(probs: dict[str, float], contrib: dict[str, float], month: int) -> str:
    terms = sorted((c for c in contrib if contrib[c] > 0), key=lambda c: -contrib[c])
    shown = [
        f"{_num(probs[c], 2)} {c} × pondere {rules.weight(c):g} × "
        f"{_num(loss.loss_kwh_day(c, month), 3)} kWh"
        for c in terms[:SHOWN_TERMS]
    ]
    more = " + …" if len(terms) > SHOWN_TERMS else ""
    return " + ".join(shown) + more if shown else "0"


def finding_fields(prediction: Prediction, delta_t_k: float, month: int) -> dict:
    """Prediction + ΔT → the Finding fields owned by the decision layer (ADR 0001).

    Score = expected risk over the calibrated probabilities. Urgency comes from the class
    with the largest contribution, unless the safety rule (ΔT ≥ 20 K) makes it critical.
    Crew, part and hours follow the model's class. `rule_applied` belongs in
    `Finding.evidence`; the rest are top-level Finding fields.
    """
    probs = prediction.probs
    contrib = contributions(probs, month)
    top = max(contrib, key=lambda c: (contrib[c], probs[c]))
    level, _, urgency_rule = rules.urgency(top, delta_t_k)
    work = rules.apply(prediction.cls, delta_t_k)
    score = round(sum(contrib.values()), 3)
    kwh = round(sum(p * loss.loss_kwh_day(c, month) for c, p in probs.items()), 3)
    risk = _risk_text(probs, contrib, month)
    return {
        "urgency": level,
        "loss_kwh_day": kwh,
        "loss_ron_day": loss.loss_ron_day(kwh),
        "score": score,
        "crew": work["crew"],
        "part": work["part"],
        "est_hours": work["est_hours"],
        "rule_applied": f"risc așteptat: {risk} = scor {_num(score, 3)}; {urgency_rule}"
        f" · verificare: {work['check']}",
    }


def prioritised(findings: list[Finding]) -> list[Finding]:
    """Criticals first, then highest score; ties → higher confidence, then finding id."""
    by_id = sorted(findings, key=lambda f: f.id)
    return sorted(
        by_id,
        key=lambda f: (f.urgency == "critical", f.score, f.prediction.probs[f.prediction.cls]),
        reverse=True,
    )


def work_orders(findings: list[Finding], modules: list[Module], created_at: str) -> list[WorkOrder]:
    """Every finding gets an order (ADR 0001); the review only overrides it.

    Unsure, not reviewed → "verify_and_repair". Rejected → no order.
    Confirmed → plain "pending". Inconclusive → reinspection.
    """
    by_id = {m.id: m for m in modules}
    reinspection = rules.load_rules()["reinspection"]
    orders = []
    for f in prioritised(findings):
        if f.review == "rejected":
            continue
        module = by_id[f.module_id]
        verify = f.prediction.unsure and f.review is None
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
            ticket_status="verify_and_repair" if verify else "pending",
        )
        if f.review == "inconclusive":
            order = order.model_copy(update={**reinspection, "ticket_status": "reinspection"})
        orders.append(order)
    return orders
