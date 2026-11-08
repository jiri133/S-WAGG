"""Hand-made findings for the decision-layer unit tests (the old mock data of ticket 05)."""

from app.schemas import Evidence, Finding, Prediction, WorkOrder
from app.services.decision import workorders
from app.services.pipeline.infer import CLASSES
from app.services.sim.park import park

TS = "2026-11-07T10:00:00Z"
MONTH = 11

# module, model class, baseline class, apparent ΔT K, unsure
ROWS = [
    ("B1-R2-T3-M07", "hot_cell", "hot_cell", 22.4, False),
    ("B1-R4-T1-M03", "diode_substring", "multi_hot", 9.8, False),
    ("B2-R1-T2-M11", "module_offline", "module_offline", 3.1, False),
    ("B2-R3-T4-M05", "multi_hot", "hot_cell", 12.6, True),
    ("B2-R5-T1-M09", "soiling", "ok", 2.2, False),
]


def finding(i: int, row: tuple) -> Finding:
    module_id, cls, base, dt, unsure = row
    fid = f"F-{i:03d}"
    # 0.01 on every other class, the rest on a second fault: the model hesitates between two
    # faults, so the finding is unsure but not on the watch list (p(ok) stays under 0.10).
    top = 0.55 if unsure else 0.93
    probs = {c: 0.01 for c in CLASSES}
    second = "soiling" if cls == "other" else "other"
    probs[second] = round(1 - top - 0.01 * (len(CLASSES) - 2), 2)
    probs[cls] = top
    prediction = Prediction(
        cls=cls,
        probs=probs,
        temperature=1.42,
        unsure=unsure,
        unsure_reason="probabilitate sub prag pe clasă de risc" if unsure else None,
    )
    fields = workorders.finding_fields(prediction, dt, MONTH)
    rule = fields.pop("rule_applied")
    return Finding(
        id=fid,
        module_id=module_id,
        prediction=prediction,
        baseline_cls=base,
        **fields,
        evidence=Evidence(
            frame_ids=[],
            crop_url=f"/api/findings/{fid}/crop.png",
            delta_t_k=dt,
            pattern="test",
            seen_in_both_passes=True,
            rule_applied=rule,
        ),
    )


def findings() -> list[Finding]:
    return [finding(i, row) for i, row in enumerate(ROWS, start=1)]


def work_orders() -> list[WorkOrder]:
    return workorders.work_orders(findings(), park(), TS)
