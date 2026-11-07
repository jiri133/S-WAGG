"""The six robustness cases of DESIGN_SPEC §6, through the simulator and the whole pipeline.

Each test drives the real steps — regenerate the frames from `MissionSettings`, then
`check.frame` → `register` → `infer` → `calibrate` → `consistency.merge` — instead of feeding
hand-made predictions. Helpers are reused from `tests.test_pipeline`.
"""

import numpy as np
import pytest

from app.schemas import MissionSettings
from app.services.pipeline import check, consistency, infer, register
from app.services.sim import artefacts, compose
from app.services.sim.park import tables
from tests.test_pipeline import (
    CLEAN,
    NAMES,
    _glare_truth,
    _outcomes,
    _table_predictions,
    checked,
)


@pytest.fixture(scope="module")
def model():
    return infer.load_model()


def _lost_passes(settings: MissionSettings) -> dict[str, int]:
    """Table → how many of its two passes were lost (0, 1 or 2)."""
    plan = artefacts.plan(settings)
    return {table: sum(f["lost"] for f in plan if f["table"] == table) for table in NAMES}


# --- 1. missing frame -------------------------------------------------------


def test_a_missing_frame_uses_the_other_pass_and_two_lost_passes_are_not_inspected(model):
    s = MissionSettings(**{**CLEAN, "p_lost": 0.5})
    lost = _lost_passes(s)
    one_lost = {t for t, n in lost.items() if n == 1}
    both_lost = {t for t, n in lost.items() if n == 2}
    assert one_lost and both_lost  # the seed fixes which tables lose which passes

    not_inspected = check.not_inspected_tables(checked(s), tables())
    assert set(not_inspected) == both_lost  # the refly proposal: the tables with no usable frame
    assert set(not_inspected.values()) == {"niciun cadru livrat"}

    covered_with_one = {}
    for table in one_lost:
        passes = _table_predictions(s, table, model)
        [survivor] = passes  # the delivered pass is used as is
        merged = consistency.merge(passes)
        assert len(merged) == 12
        assert all(o.passes == (survivor,) and not o.seen_in_both_passes for o in merged.values())
        covered_with_one[table] = len(merged)

    covered_with_two = {table: len(_table_predictions(s, table, model)) for table in both_lost}

    assert set(covered_with_one.values()) == {12}  # one pass covers the whole table
    assert set(covered_with_two.values()) == {0}  # two lost passes cover no module


# --- 2. irradiance under 600 W/m² -------------------------------------------


def test_low_irradiance_frames_are_rejected_and_leave_no_findings(model):
    s = MissionSettings(**{**CLEAN, "inject": ["low_irr"]})
    frames = checked(s)
    rejected = [f for f in frames if not f.check_ok]
    assert len(rejected) == 2
    assert all(any("iradianță" in p for p in f.problems) for f in rejected)
    [table] = {f.table for f in rejected}

    not_inspected = check.not_inspected_tables(frames, tables())
    assert set(not_inspected) == {table} and "iradianță" in not_inspected[table]
    assert _table_predictions(s, table, model) == {}  # rejected frames never reach the model

    cloudy = MissionSettings(**{**CLEAN, "p_cloud": 1})
    cloudy_frames = checked(cloudy)
    assert all(not f.check_ok for f in cloudy_frames)  # every table under 600 W/m²
    assert set(check.not_inspected_tables(cloudy_frames, tables())) == set(NAMES)
    assert all(_table_predictions(cloudy, table, model) == {} for table in NAMES)


# --- 3. RGB frame -----------------------------------------------------------


def test_rgb_frames_are_rejected_by_the_data_check(model):
    s = MissionSettings(**{**CLEAN, "inject": ["rgb"]})
    frames = checked(s)
    rejected = [f for f in frames if not f.check_ok]
    assert len(rejected) == 2
    for f in rejected:
        assert any("radiometric" in p for p in f.problems)
        assert any("3 canale" in p for p in f.problems)
    [table] = {f.table for f in rejected}
    assert table in check.not_inspected_tables(frames, tables())
    assert _table_predictions(s, table, model) == {}


# --- 4. frame without panels ------------------------------------------------


def test_frames_without_panels_are_rejected(model):
    s = MissionSettings(**{**CLEAN, "inject": ["no_panels"]})
    frames = checked(s)
    rejected = [f for f in frames if not f.check_ok]
    assert len(rejected) == 2
    assert all(any("grilă" in p for p in f.problems) for f in rejected)
    [table] = {f.table for f in rejected}
    assert table in check.not_inspected_tables(frames, tables())
    assert _table_predictions(s, table, model) == {}


# --- 5. glare ---------------------------------------------------------------


def test_glare_is_a_probable_reflection_in_the_review_queue(model):
    s = MissionSettings(**{**CLEAN, "p_glare": 1, "n_faults": 0})
    before, findings, queue = set(), set(), set()
    for table in NAMES:
        passes = _table_predictions(s, table, model)
        merged = consistency.merge(passes)
        glare_pass, hit = _glare_truth(s, table)
        for module_id, outcome in merged.items():
            anomalous = [no for no, preds in passes.items() if preds[module_id].cls != "ok"]
            if anomalous:
                before.add(module_id)  # without step 4 this would be reported as a finding
            if len(anomalous) == 1 and len(passes) == 2:
                assert outcome.reflection, module_id
            if outcome.reflection:
                queue.add(module_id)
                assert (outcome.prediction.unsure, outcome.urgency) == (True, "low")
                assert "reflexie probabilă" in outcome.prediction.unsure_reason
                assert anomalous == [glare_pass] and module_id in hit
            elif outcome.prediction.cls != "ok":
                findings.add(module_id)
                assert len(anomalous) == 2

    assert queue  # the simulated glare is visible to the model in exactly one pass
    assert queue.isdisjoint(findings)  # no probable reflection is reported as a finding
    assert before == queue | findings  # consistency sorts every anomaly and adds none


# --- 6. GPS offset ----------------------------------------------------------


def test_gps_offset_is_detected_corrected_and_gives_the_aligned_outcomes(model):
    aligned_settings = MissionSettings(**CLEAN)
    shifted_settings = MissionSettings(**{**CLEAN, "p_gps": 1})
    truth = {f["id"]: f["gps"] for f in artefacts.plan(shifted_settings)}
    aligned_frames = {m.id: m for m in compose.frames(aligned_settings)}

    for meta in compose.frames(shifted_settings):
        img = compose.frame_image(shifted_settings, meta.id)
        gps = register.offset(img)
        assert gps == truth[meta.id] and gps != 0  # every shifted frame is detected
        reference = compose.frame_image(aligned_settings, aligned_frames[meta.id].id)
        got, want = register.slots(img, gps), register.slots(reference, 0)
        assert set(got) == set(range(1, 13)) - ({6, 12} if gps == -1 else {1, 7})
        for pos in got:
            np.testing.assert_array_equal(got[pos], want[pos])

    aligned = _outcomes(aligned_settings, model)
    shifted = _outcomes(shifted_settings, model)
    common = {
        mid
        for mid in set(aligned) & set(shifted)
        if aligned[mid].seen_in_both_passes and shifted[mid].seen_in_both_passes
    }
    assert len(common) >= 320  # ±1 hides at most 2 modules per pass, so ≥ 8 of 12 per table
    for module_id in common:
        a, b = aligned[module_id], shifted[module_id]
        assert (
            a.prediction.cls,
            a.prediction.unsure,
            a.prediction.unsure_reason,
            a.reflection,
            a.urgency,
            a.passes,
        ) == (
            b.prediction.cls,
            b.prediction.unsure,
            b.prediction.unsure_reason,
            b.reflection,
            b.urgency,
            b.passes,
        )
        assert np.allclose(list(a.prediction.probs.values()), list(b.prediction.probs.values()))
