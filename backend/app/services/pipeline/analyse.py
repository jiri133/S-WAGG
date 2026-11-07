"""Steps 2–4 (DESIGN_SPEC §5) over a whole flight: checked frames → findings.

Per table and pass: the registered slots go through the model and calibration, and each
module's apparent ΔT is its hottest point against its own median (GLOSSARY, `delta_t`). The two
passes are merged by `consistency`. The ΔT kept is the lower of the passes, so a reflection in
one pass never trips the safety rule. A module becomes a finding unless the model says `ok` and
its ΔT is under the safety threshold.
"""

from typing import NamedTuple

import numpy as np
import onnxruntime as ort

from app.schemas import Evidence, Finding, FrameMeta, Prediction
from app.services.baseline import features, rules_classifier
from app.services.decision import rules, workorders
from app.services.pipeline import calibrate, consistency, infer, register
from app.services.sim import artefacts, compose
from app.services.sim.park import tables


class Look(NamedTuple):
    """One module in one pass."""

    prediction: Prediction
    crop: np.ndarray  # uint8 (40, 24) gray, what the model saw
    delta_t_k: float


def table_looks(
    frames: list[tuple[FrameMeta, np.ndarray]],
    table: str,
    model: ort.InferenceSession,
    temperature: float,
    thresholds: dict,
) -> dict[int, dict[str, Look]]:
    """{pass_no: {module_id: Look}} from the table's frames that passed the data check."""
    ids = {m.pos: m.id for m in tables()[table]}
    out: dict[int, dict[str, Look]] = {}
    for meta, img in frames:
        if meta.table != table or not meta.check_ok:
            continue
        slots = register.slots(img, meta.gps_offset_detected)
        pos = sorted(slots)
        t_base = artefacts.t_base(meta.irradiance_wm2)
        gray = np.stack([compose.to_gray(slots[p], t_base) for p in pos])
        probs = infer.probs(model, gray, temperature)
        preds = calibrate.predictions(probs, temperature, thresholds)
        crops = np.clip(np.rint(gray), 0, 255).astype(np.uint8)
        out[meta.pass_no] = {
            ids[p]: Look(pred, crop, delta_t(slots[p]))
            for p, pred, crop in zip(pos, preds, crops, strict=True)
        }
    return out


def delta_t(slot: np.ndarray) -> float:
    """Apparent ΔT in K: the module's hottest point against its own median.

    Against the table's median, a module that is warm all over (a brighter Raptor crop, a broad
    shadow) tripped the 20 K rule: on 20 seeds, 57 of 70 alerts were on ok, soiling or shadow
    modules. Against its own median only a local hot spot counts: 11 of 19.
    """
    return float(slot.max() - np.median(slot))


def pattern(crop: np.ndarray) -> str:
    """The thermal pattern in words, from the baseline's features."""
    f = features.extract(crop.astype(np.float64))
    return (
        f"{int(f['n_blobs'])} zone fierbinți, {f['hot_frac']:.0%} din modul fierbinte, "
        f"contrast pe substring {f['band_contrast']:.0f} niveluri"
    )


def _finding(
    fid: str, module_id: str, table: str, o: consistency.Outcome, look: Look, dt: float, month: int
) -> Finding:
    fields = workorders.finding_fields(o.prediction, dt, month)
    rule = fields.pop("rule_applied")
    if o.urgency and fields["urgency"] != "critical":  # a probable reflection waits for review
        fields["urgency"] = o.urgency
        rule += f"; reflexie probabilă → urgență {o.urgency}"
    return Finding(
        id=fid,
        module_id=module_id,
        prediction=o.prediction,
        baseline_cls=rules_classifier.classify(look.crop.astype(np.float64)),
        **fields,
        evidence=Evidence(
            frame_ids=[f"FR-{table}-P{no}" for no in o.passes],
            crop_url=f"/api/findings/{fid}/crop.png",
            gradcam_url=f"/api/findings/{fid}/gradcam.png",
            delta_t_k=dt,
            pattern=pattern(look.crop),
            seen_in_both_passes=o.seen_in_both_passes,
            rule_applied=rule,
        ),
    )


def findings(
    frames: list[tuple[FrameMeta, np.ndarray]],
    model: ort.InferenceSession,
    temperature: float,
    thresholds: dict,
    month: int,
) -> tuple[list[tuple[Finding, np.ndarray]], set[str]]:
    """Findings in flight order, each with its crop, and the ids of every imaged module."""
    safety_k = rules.load_rules()["safety"]["delta_t_min_k"]
    out, imaged = [], set()
    for table in tables():
        looks = table_looks(frames, table, model, temperature, thresholds)
        merged = consistency.merge(
            {no: {m: lk.prediction for m, lk in mods.items()} for no, mods in looks.items()}
        )
        for module_id, o in merged.items():
            imaged.add(module_id)
            dt = round(min(looks[no][module_id].delta_t_k for no in o.passes), 1)
            if o.prediction.cls == "ok" and dt < safety_k:
                continue
            # The crop of the pass whose prediction is reported (the anomalous one if alone).
            no = next(n for n in o.passes if looks[n][module_id].prediction.cls == o.prediction.cls)
            look = looks[no][module_id]
            fid = f"F-{len(out) + 1:03d}"
            out.append((_finding(fid, module_id, table, o, look, dt, month), look.crop))
    return out, imaged
