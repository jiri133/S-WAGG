"""Pipeline steps 1, 2 and 4 (DESIGN_SPEC §5) on the simulator, plus the frames endpoint."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import FrameMeta, MissionSettings, Prediction
from app.services.pipeline import analyse, calibrate, check, consistency, infer, register
from app.services.sim import artefacts, compose
from app.services.sim.park import SLOT_W, tables

CLEAN = {"p_cloud": 0, "p_gps": 0, "p_glare": 0, "p_lost": 0}
NAMES = list(tables())
T = calibrate.load_temperature()
TH = calibrate.load_thresholds()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def model():
    return infer.load_model()


def checked(settings: MissionSettings) -> list[FrameMeta]:
    return [check.frame(m, compose.frame_image(settings, m.id)) for m in compose.frames(settings)]


def _pred(cls: str, p: float = 0.9) -> Prediction:
    probs = {c: round((1 - p) / len(infer.CLASSES), 4) for c in infer.CLASSES}
    probs[cls] = p
    return Prediction(cls=cls, probs=probs, temperature=1.0, unsure=False)


# --- check.py ---------------------------------------------------------------


def test_a_clean_frame_passes():
    assert all(f.check_ok and f.problems == [] for f in checked(MissionSettings(**CLEAN)))


def test_low_irradiance_is_rejected():
    s = MissionSettings(**{**CLEAN, "inject": ["low_irr"]})
    bad = [f for f in checked(s) if not f.check_ok]
    assert len(bad) == 2
    assert all(any("iradianță" in p for p in f.problems) for f in bad)


def test_high_wind_is_rejected():
    s = MissionSettings(**CLEAN)
    meta = compose.frames(s)[0]
    got = check.frame(meta.model_copy(update={"wind_ms": 9.0}), compose.frame_image(s, meta.id))
    assert not got.check_ok and any("vânt" in p for p in got.problems)


@pytest.mark.parametrize("update", [{"timestamp": ""}, {"lat": 0.0, "lon": 0.0}])
def test_missing_time_or_position_is_rejected(update):
    s = MissionSettings(**CLEAN)
    meta = compose.frames(s)[0]
    got = check.frame(meta.model_copy(update=update), compose.frame_image(s, meta.id))
    assert not got.check_ok and "fără timp sau poziție" in got.problems


def test_rgb_frame_is_rejected():
    s = MissionSettings(**{**CLEAN, "inject": ["rgb"]})
    bad = [f for f in checked(s) if not f.check_ok]
    assert len(bad) == 2
    assert all(any("radiometric" in p for p in f.problems) for f in bad)


def test_frame_without_panels_is_rejected():
    s = MissionSettings(**{**CLEAN, "inject": ["no_panels"]})
    bad = [f for f in checked(s) if not f.check_ok]
    assert len(bad) == 2
    assert all(any("grilă" in p for p in f.problems) for f in bad)


@pytest.mark.parametrize("kind", ["too_hot", "nan"])
def test_invalid_temperatures_are_rejected(kind):
    s = MissionSettings(**CLEAN)
    meta = compose.frames(s)[0]
    img = compose.frame_image(s, meta.id)
    if kind == "too_hot":
        img = img + 200.0
    else:
        img = img.copy()
        img[0, 0] = np.nan
    got = check.frame(meta, img)
    assert not got.check_ok and any("temperaturi invalide" in p for p in got.problems)


def test_tables_without_a_usable_frame_are_not_inspected():
    cloudy = MissionSettings(**{**CLEAN, "p_cloud": 1})
    bad = check.not_inspected_tables(checked(cloudy), tables())
    assert set(bad) == set(NAMES)
    assert all("iradianță" in reason for reason in bad.values())
    assert check.not_inspected_tables(checked(MissionSettings(**CLEAN)), tables()) == {}


def test_missing_injection_leaves_the_table_without_frames():
    s = MissionSettings(**{**CLEAN, "inject": ["missing"]})
    bad = check.not_inspected_tables(checked(s), tables())
    assert list(bad.values()) == ["niciun cadru livrat"]


def test_one_lost_pass_still_leaves_the_table_inspected():
    s = MissionSettings(**{**CLEAN, "p_lost": 0.5})
    delivered = compose.frames(s)
    with_frames = {f.table for f in delivered}
    assert check.not_inspected_tables(checked(s), tables()) == {
        t: "niciun cadru livrat" for t in set(NAMES) - with_frames
    }
    assert any(sum(f.table == t for f in delivered) == 1 for t in with_frames)  # a single pass


# --- register.py ------------------------------------------------------------


def _frame_with_ground(side: int) -> np.ndarray:
    img = np.full((80, 144), 46.0, np.float32)  # modules warm, no ground
    img[:, :SLOT_W] = 28.0 if side < 0 else img[:, :SLOT_W]
    img[:, -SLOT_W:] = 28.0 if side > 0 else img[:, -SLOT_W:]
    return img


@pytest.mark.parametrize(("side", "missing"), [(-1, {6, 12}), (1, {1, 7})])
def test_offset_and_missing_positions(side, missing):
    img = _frame_with_ground(side)
    assert register.offset(img) == side
    assert set(register.slots(img, side)) == set(range(1, 13)) - missing


def test_aligned_flight_has_no_offset():
    s = MissionSettings(**CLEAN)
    assert {register.offset(compose.frame_image(s, m.id)) for m in compose.frames(s)} == {0}


def test_gps_offset_is_detected_on_the_simulator():
    s = MissionSettings(**{**CLEAN, "p_gps": 1})
    truth = {f["id"]: f["gps"] for f in artefacts.plan(s)}
    got = {m.id: register.offset(compose.frame_image(s, m.id)) for m in compose.frames(s)}
    assert got == {fid: truth[fid] for fid in got}
    assert set(got.values()) == {-1, 1}


def test_slots_are_realigned_to_the_aligned_frame():
    shifted, aligned = MissionSettings(**{**CLEAN, "p_gps": 1}), MissionSettings(**CLEAN)
    reference = {m.id: compose.frame_image(aligned, m.id) for m in compose.frames(aligned)}
    for meta in compose.frames(shifted):
        img = compose.frame_image(shifted, meta.id)
        gps = register.offset(img)
        got, want = register.slots(img, gps), register.slots(reference[meta.id], 0)
        for pos in got:
            np.testing.assert_array_equal(got[pos], want[pos])


def test_a_gray_level_crop_round_trips_through_temperature():
    crop = compose.crops()["ok"][0]
    temp = compose.to_temperature(crop, 46.0)
    np.testing.assert_allclose(compose.to_gray(temp, 46.0), crop, atol=1e-5)


# --- consistency.py ---------------------------------------------------------


def test_an_anomaly_seen_in_both_passes_is_a_finding():
    a, b = _pred("diode_substring"), _pred("diode_substring", 0.8)
    [outcome] = consistency.merge({1: {"m": a}, 2: {"m": b}}).values()
    assert (outcome.reflection, outcome.seen_in_both_passes, outcome.urgency) == (False, True, None)
    assert outcome.prediction.cls == "diode_substring"


def test_a_lone_anomaly_is_a_probable_reflection_in_the_queue():
    [outcome] = consistency.merge({1: {"m": _pred("hot_cell")}, 2: {"m": _pred("ok")}}).values()
    assert outcome.reflection and outcome.seen_in_both_passes and outcome.urgency == "low"
    assert outcome.prediction.unsure
    assert "reflexie probabilă" in outcome.prediction.unsure_reason
    assert "trecerea 1" in outcome.prediction.unsure_reason


def test_a_missing_pass_uses_the_other_one():
    [outcome] = consistency.merge({2: {"m": _pred("soiling")}}).values()
    assert outcome.passes == (2,)
    assert (outcome.reflection, outcome.seen_in_both_passes) == (False, False)
    assert outcome.urgency is None
    assert outcome.prediction.cls == "soiling"


def test_two_ok_passes_stay_ok():
    [outcome] = consistency.merge({1: {"m": _pred("ok")}, 2: {"m": _pred("ok")}}).values()
    assert outcome.prediction.cls == "ok" and not outcome.reflection


def test_disagreeing_anomalies_use_the_more_confident_pass():
    [outcome] = consistency.merge(
        {1: {"m": _pred("hot_cell", 0.6)}, 2: {"m": _pred("multi_hot", 0.95)}}
    ).values()
    assert outcome.prediction.cls == "multi_hot"
    assert (outcome.reflection, outcome.seen_in_both_passes) == (False, True)


def test_a_module_seen_in_no_pass_is_absent():
    merged = consistency.merge({1: {"a": _pred("ok")}, 2: {"b": _pred("ok")}})
    assert set(merged) == {"a", "b"}


# --- the whole pipeline on the simulator ------------------------------------


def _table_predictions(settings: MissionSettings, table: str, model) -> dict[int, dict]:
    """{pass_no: {module_id: Prediction}} for one table, through the mission's analysis."""
    frames = []
    for meta in (m for m in compose.frames(settings) if m.table == table):
        img = compose.frame_image(settings, meta.id)
        meta = check.frame(meta, img)
        if meta.check_ok:
            meta = meta.model_copy(update={"gps_offset_detected": register.offset(img)})
        frames.append((meta, img))
    looks = analyse.table_looks(frames, table, model, T, TH)
    return {no: {m: lk.prediction for m, lk in mods.items()} for no, mods in looks.items()}


_OUTCOMES: dict[str, dict] = {}  # test_robustness analyses the same two GPS flights


def _outcomes(settings: MissionSettings, model) -> dict:
    key = settings.model_dump_json()
    if key not in _OUTCOMES:
        out = {}
        for table in NAMES:
            out.update(consistency.merge(_table_predictions(settings, table, model)))
        _OUTCOMES[key] = out
    return _OUTCOMES[key]


def test_full_pipeline_over_every_table(model):
    s = MissionSettings(**{**CLEAN, "p_glare": 1, "p_gps": 0.3, "p_lost": 0.05})
    for table in NAMES:
        passes = _table_predictions(s, table, model)
        imaged = set().union(*(p.keys() for p in passes.values())) if passes else set()
        merged = consistency.merge(passes)
        assert set(merged) == imaged
        for outcome in merged.values():
            assert outcome.prediction.probs
            if outcome.reflection:
                assert outcome.prediction.unsure and outcome.urgency == "low"


def test_gps_correction_gives_the_aligned_predictions(model):
    aligned = _outcomes(MissionSettings(**CLEAN), model)
    shifted = _outcomes(MissionSettings(**{**CLEAN, "p_gps": 1}), model)
    common = {
        mid
        for mid in set(aligned) & set(shifted)
        if aligned[mid].seen_in_both_passes and shifted[mid].seen_in_both_passes
    }
    assert len(common) >= 320  # a ±1 offset hides at most 2 modules per pass, so ≥8 of 12
    for module_id in common:
        a, b = aligned[module_id], shifted[module_id]
        assert (a.prediction.cls, a.reflection, a.passes) == (
            b.prediction.cls,
            b.reflection,
            b.passes,
        )
        assert np.allclose(list(a.prediction.probs.values()), list(b.prediction.probs.values()))


def _glare_truth(settings: MissionSettings, table: str) -> tuple[int, set[str]]:
    glare = next(f for f in artefacts.plan(settings) if f["table"] == table and f["glare"])
    y, x, _ = glare["glare"]
    hit = set()
    for m in tables()[table]:
        row, col = divmod(m.pos - 1, 6)
        if y < row * 40 + 40 and y + 8 > row * 40 and x < col * 24 + 24 and x + 8 > col * 24:
            hit.add(m.id)
    return glare["pass_no"], hit


def test_a_glare_only_anomaly_goes_to_the_queue():
    s = MissionSettings(**{**CLEAN, "p_glare": 1, "n_faults": 0})
    for table in NAMES:
        glare_pass, hit = _glare_truth(s, table)
        passes = {
            p: {
                m.id: _pred("hot_cell" if p == glare_pass and m.id in hit else "ok")
                for m in tables()[table]
            }
            for p in (1, 2)
        }
        reflections = {mid: o for mid, o in consistency.merge(passes).items() if o.reflection}
        assert set(reflections) == hit
        assert all(o.prediction.unsure and o.urgency == "low" for o in reflections.values())


# --- the frames endpoint runs steps 1–2 -------------------------------------


def test_frames_endpoint_reports_the_check(client):
    frames = [FrameMeta.model_validate(x) for x in client.get("/api/missions/M-0001/frames").json()]
    settings = MissionSettings.model_validate(client.get("/api/missions/M-0001").json()["settings"])
    plan = artefacts.plan(settings)
    assert {f.id for f in frames} == {f["id"] for f in plan if not f["lost"]}
    assert all(f.check_ok == (not f.problems) for f in frames)
    assert all(f.problems for f in frames if not f.check_ok)
