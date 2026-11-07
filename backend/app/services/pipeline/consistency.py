"""Step 4 (DESIGN_SPEC §5): merge the two passes over a table.

An anomaly seen in both passes is a finding. An anomaly seen in only one pass of a table whose
other pass is available is a **probable reflection** (glare): it goes to the review queue with
low urgency, and the engineer confirms it. When one pass is missing, the other one is used as is.

The caller builds `{pass_no: {module_id: Prediction}}` from the registered slots and
`calibrate.predictions`, calls `merge`, then turns each outcome into a `Finding`. A module absent
from every pass has no image and is `not_inspected`; `merge` never invents it.
"""

from typing import NamedTuple

from app.schemas import Prediction, Urgency


class Outcome(NamedTuple):
    prediction: Prediction  # the class to report; a reflection is already unsure
    passes: tuple[int, ...]  # passes that had an image of the module
    seen_in_both_passes: bool
    reflection: bool  # anomaly in exactly one of two available passes
    urgency: Urgency | None  # "low" for a probable reflection, else the decision rules decide


def merge(passes: dict[int, dict[str, Prediction]]) -> dict[str, Outcome]:
    """Per module: the pass agreement, the prediction to report and the reflection flag."""
    ids = sorted(set().union(*(p.keys() for p in passes.values()))) if passes else []
    out = {}
    for module_id in ids:
        seen = {no: preds[module_id] for no, preds in passes.items() if module_id in preds}
        anomalies = {no: p for no, p in seen.items() if p.cls != "ok"}
        reflection = len(seen) > 1 and len(anomalies) == 1
        if reflection:
            pass_no, hit = next(iter(anomalies.items()))
            prediction = hit.model_copy(
                update={
                    "unsure": True,
                    "unsure_reason": (
                        f"reflexie probabilă: anomalie doar în trecerea {pass_no} ({hit.cls})"
                    ),
                }
            )
            urgency: Urgency | None = "low"
        elif anomalies:
            prediction = max(anomalies.values(), key=lambda p: p.probs[p.cls])
            urgency = None
        else:
            prediction = max(seen.values(), key=lambda p: p.probs["ok"])
            urgency = None
        out[module_id] = Outcome(
            prediction=prediction,
            passes=tuple(sorted(seen)),
            seen_in_both_passes=len(seen) > 1,
            reflection=reflection,
            urgency=urgency,
        )
    return out
