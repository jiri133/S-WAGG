"""Simulator (DESIGN_SPEC §4): layout, same seed → same frames, every injection from settings."""

import csv
import hashlib
import inspect
import math
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.main import app
from app.schemas import FrameMeta, MissionSettings
from app.services import state
from app.services.sim import artefacts, compose
from app.services.sim.park import park, tables

CLEAN = {"p_cloud": 0, "p_gps": 0, "p_glare": 0, "p_lost": 0}  # no random artefacts
ALL_INJECTIONS = list(artefacts.INJECTIONS)


def digest(settings: MissionSettings) -> str:
    """Hash of every delivered frame: metadata and pixels."""
    h = hashlib.sha256()
    for meta in compose.frames(settings):
        h.update(meta.model_dump_json().encode())
        h.update(compose.frame_image(settings, meta.id).tobytes())
    return h.hexdigest()


def slot(img: np.ndarray, pos: int) -> np.ndarray:
    half, col = divmod(pos - 1, 6)
    return img[half * 40 : (half + 1) * 40, col * 24 : (col + 1) * 24]


def injected(settings: MissionSettings) -> list[dict]:
    return [f for f in artefacts.plan(settings) if f["inject"]]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_park_layout():
    modules = park()
    assert len(modules) == 480 and len({m.id for m in modules}) == 480
    assert len(tables()) == 40 and {len(ms) for ms in tables().values()} == {12}
    strings, inverters = Counter(m.string for m in modules), Counter(m.inverter for m in modules)
    assert (len(strings), set(strings.values())) == (20, {24})
    assert (len(inverters), set(inverters.values())) == (10, {48})
    m = next(m for m in modules if m.id == "B1-R2-T3-M07")
    assert (m.table, m.string, m.inverter) == ("B1-R2-T3", "B1-R2-S2", "INV-1.2")
    corner = {m.table: m for m in modules if m.pos == 1}
    assert corner["B1-R2-T1"].y_m - corner["B1-R1-T1"].y_m == 9.0  # rows 9 m apart
    assert corner["B2-R1-T1"].x_m - corner["B1-R1-T1"].x_m == 45.0  # blocks 45 m apart


def test_same_seed_same_frames():
    s = MissionSettings(inject=ALL_INJECTIONS, p_gps=0.3, p_glare=0.5)
    assert digest(s) == digest(MissionSettings(**s.model_dump()))
    assert digest(s) != digest(MissionSettings(**{**s.model_dump(), "seed": 8}))


def test_same_seed_same_frames_in_another_process():
    """Frames are regenerated on every request, even after a restart (new hash seed)."""
    code = (  # the same digest(), without importing pytest and the whole app
        "import hashlib\n"
        "from app.schemas import MissionSettings\n"
        "from app.services.sim import compose\n"
        f"{inspect.getsource(digest)}\n"
        f"print(digest(MissionSettings(inject={ALL_INJECTIONS!r})))\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    backend = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=backend, env=env, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == digest(MissionSettings(inject=ALL_INJECTIONS))


def test_faults_are_planted_from_the_seed():
    truth = compose.truth(MissionSettings(n_faults=12))
    assert set(truth) == {m.id for m in park()}
    assert sum(c != "ok" for c in truth.values()) == 12
    assert set(compose.truth(MissionSettings(n_faults=0)).values()) == {"ok"}
    # Artefacts never move the faults.
    noisy = MissionSettings(p_cloud=1, p_gps=1, inject=ALL_INJECTIONS)
    assert compose.truth(noisy) == compose.truth(MissionSettings())


def test_slots_are_crops_of_the_planted_class_in_apparent_temperature():
    s = MissionSettings(n_faults=48, **CLEAN)
    lib, planted, crops = compose.crops(), compose.truth(s), compose.module_crops(s)
    # Every slot holds a crop from its module's planted class ("ok" for healthy modules).
    assert all(np.shares_memory(crops[m.id], lib[planted[m.id]]) for m in park())
    meta = compose.frames(s)[0]
    img = compose.frame_image(s, meta.id)
    t_base = artefacts.t_base(meta.irradiance_wm2)
    for m in tables()[meta.table]:
        level = crops[m.id].astype(np.float32) - compose.median_ok()
        expected = t_base + level * compose.K_PER_LEVEL
        np.testing.assert_allclose(slot(img, m.pos), expected, atol=1e-4)


def test_two_passes_from_slightly_different_positions():
    flown = compose.frames(MissionSettings(**CLEAN))
    assert [m.timestamp for m in flown] == sorted(m.timestamp for m in flown)
    by_id = {m.id: m for m in flown}
    for table in list(tables())[:4]:
        p1, p2 = by_id[f"FR-{table}-P1"], by_id[f"FR-{table}-P2"]
        dx_m = (p2.lon - p1.lon) * 111_320 * math.cos(math.radians(p1.lat))
        assert p1.lat == p2.lat and abs(dx_m - 1.0) < 0.05  # 1 m apart along the row
        dt = datetime.fromisoformat(p2.timestamp) - datetime.fromisoformat(p1.timestamp)
        assert dt.total_seconds() == 4


def test_defect_in_both_passes_glare_in_one():
    s = MissionSettings(n_faults=480, **{**CLEAN, "p_glare": 1})
    for table in tables():
        passes = [f for f in artefacts.plan(s) if f["table"] == table]
        assert sum(f["glare"] is not None for f in passes) == 1
        diff = compose.frame_image(s, f"FR-{table}-P1") - compose.frame_image(s, f"FR-{table}-P2")
        changed = np.abs(diff) > 1e-4
        assert changed.sum() == 8 * 8  # only the 2×2 cells of glare differ
        assert np.all((np.abs(diff[changed]) >= 7) & (np.abs(diff[changed]) <= 11))


def test_cloud_lowers_irradiance_and_temperature():
    sunny, cloudy = MissionSettings(**CLEAN), MissionSettings(**{**CLEAN, "p_cloud": 1})
    for a, b in zip(compose.frames(sunny)[:6], compose.frames(cloudy)[:6], strict=True):
        assert a.irradiance_wm2 >= 800 and 420 <= b.irradiance_wm2 <= 480
        warm, cold = compose.frame_image(sunny, a.id), compose.frame_image(cloudy, b.id)
        assert np.median(cold) < np.median(warm) - 8


def test_gps_offset_shifts_the_table_and_shows_ground():
    shifted, aligned = MissionSettings(**{**CLEAN, "p_gps": 1}), MissionSettings(**CLEAN)
    signs = set()
    for f in artefacts.plan(shifted)[:10]:
        img, ref = compose.frame_image(shifted, f["id"]), compose.frame_image(aligned, f["id"])
        signs.add(f["gps"])
        if f["gps"] == 1:  # looked one module further along +x: ground on the right
            ground, kept, moved = img[:, 120:], img[:, :120], ref[:, 24:]
        else:
            ground, kept, moved = img[:, :24], img[:, 24:], ref[:, :120]
        assert abs(float(ground.mean()) - 28.0) < 0.3
        np.testing.assert_array_equal(kept, moved)
    assert signs == {-1, 1}


def test_lost_frames_are_absent():
    assert len(compose.frames(MissionSettings(**CLEAN))) == 80
    assert compose.frames(MissionSettings(p_lost=1)) == []
    assert compose.frame_image(MissionSettings(p_lost=1), "FR-B1-R1-T1-P1") is None


@pytest.mark.parametrize("inject", ALL_INJECTIONS)
def test_each_injection_hits_both_passes_of_one_table(inject):
    s = MissionSettings(inject=[inject], **CLEAN)
    hit = injected(s)
    assert [f["pass_no"] for f in hit] == [1, 2] and hit[0]["table"] == hit[1]["table"]
    delivered = {m.id: m for m in compose.frames(s)}
    assert len(delivered) == (78 if inject == "missing" else 80)
    for f in hit:
        if inject == "missing":
            assert f["id"] not in delivered
            continue
        meta, img = delivered[f["id"]], compose.frame_image(s, f["id"])
        if inject == "rgb":
            assert (meta.channels, meta.radiometric) == (3, False)
            assert (img.shape, img.dtype) == ((80, 144, 3), np.uint8)
        elif inject == "no_panels":
            assert abs(float(img.mean()) - 28.0) < 0.2 and float(img.std()) < 1
        else:
            assert meta.irradiance_wm2 < 600 and (meta.channels, meta.radiometric) == (1, True)


def test_injections_together_keep_their_own_tables():
    together = {f["inject"]: f["table"] for f in injected(MissionSettings(inject=ALL_INJECTIONS))}
    assert len(set(together.values())) == 4
    for inject, table in together.items():
        assert {f["table"] for f in injected(MissionSettings(inject=[inject]))} == {table}


def test_a_higher_probability_only_adds_its_own_artefact():
    base, cloudier = artefacts.plan(MissionSettings()), artefacts.plan(MissionSettings(p_cloud=0.5))
    for a, b in zip(base, cloudier, strict=True):
        assert (a["gps"], a["glare"], a["lost"]) == (b["gps"], b["glare"], b["lost"])
        assert b["cloud"] or not a["cloud"]


def test_synthetic_crops_stand_in_without_raptor(monkeypatch, tmp_path):
    monkeypatch.setattr(compose, "TEST_CSV", tmp_path / "missing.csv")
    compose.crops.cache_clear()
    compose.median_ok.cache_clear()
    try:
        lib = compose.crops()
        assert set(lib) == set(compose.CLASSES)
        assert all(a.shape[1:] == (40, 24) and a.dtype == np.uint8 for a in lib.values())
        s = MissionSettings()
        assert compose.frame_image(s, compose.frames(s)[0].id).shape == (80, 144)
    finally:
        compose.crops.cache_clear()
        compose.median_ok.cache_clear()


@pytest.mark.skipif(
    not (compose.ROOT / "data" / "raptor").is_dir(),
    reason="Raptor crops not downloaded (uv run --project ml python ml/data.py)",
)
def test_real_crops_come_from_the_test_split():
    with compose.TEST_CSV.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    lib = compose.crops()
    assert {c: len(a) for c, a in lib.items()} == Counter(r["class"] for r in rows)
    first = rows[0]
    with Image.open(compose.ROOT / first["path"]) as im:
        np.testing.assert_array_equal(lib[first["class"]][0], np.asarray(im.convert("L")))


def test_frames_endpoint_serves_the_simulator(client):
    res = client.get("/api/missions/M-0001/frames")
    assert res.status_code == 200
    frames = [FrameMeta.model_validate(x) for x in res.json()]
    settings = MissionSettings.model_validate(client.get("/api/missions/M-0001").json()["settings"])
    assert [f.id for f in frames] == [f.id for f in compose.frames(settings)]
    assert all(f.check_ok == (not f.problems) for f in frames)  # ticket 17 fills these in


def test_thumb_is_the_regenerated_frame(client):
    s = MissionSettings()
    fid = compose.frames(s)[0].id
    res = client.get(f"/api/frames/{fid}/thumb.png")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    flown = state.frame_image(fid)  # the latest flown mission's frame, else the default seed's
    expected = flown if flown is not None else compose.frame_image(s, fid)
    assert res.content == compose.png(expected)
    im = Image.open(BytesIO(res.content))
    assert (im.size, im.mode) == ((144, 80), "L")


def test_rgb_thumb_has_3_channels():
    s = MissionSettings(inject=["rgb"])
    fid = injected(s)[0]["id"]
    assert Image.open(BytesIO(compose.png(compose.frame_image(s, fid)))).mode == "RGB"


def test_unknown_or_lost_frame_is_404(client):
    lost = next(f["id"] for f in artefacts.plan(MissionSettings()) if f["lost"])
    assert compose.frame_image(MissionSettings(), lost) is None  # a flown mission may have it
    assert client.get("/api/frames/FR-B9-R1-T1-P1/thumb.png").status_code == 404
    assert client.get("/api/frames/nope/thumb.png").status_code == 404


@pytest.mark.parametrize(
    "bad", [{"seed": -1}, {"seed": 2**31}, {"n_faults": 481}, {"p_glare": 1.5}, {"speed": 0}]
)
def test_settings_out_of_range_are_rejected(client, bad):
    assert client.post("/api/missions", json=bad).status_code == 422


def test_infinite_speed_is_rejected():
    # Checked on the schema: FastAPI's default 422 handler cannot echo inf back as JSON.
    with pytest.raises(ValidationError):
        MissionSettings(speed=math.inf)
