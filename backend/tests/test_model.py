"""Model in the pipeline: infer (§5 step 3), calibrate (step 5) and POST /api/analyse."""

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.baseline.features import load_crop
from app.services.pipeline import calibrate, infer

CROPS = sorted((Path(__file__).parent / "fixtures" / "crops").glob("*.jpg"))
TH = calibrate.DEFAULT_THRESHOLDS


@pytest.fixture(scope="module")
def model():
    return infer.load_model()


def _p(**probs: float) -> np.ndarray:
    return np.array([probs.get(c, 0.0) for c in infer.CLASSES])


def test_infer_batch_gives_probabilities(model):
    crops = np.stack([load_crop(p) for p in CROPS])
    p = infer.probs(model, crops, temperature=1.0)
    assert p.shape == (len(CROPS), 8)
    assert np.allclose(p.sum(axis=1), 1.0, atol=1e-5)


def test_higher_temperature_flattens(model):
    crop = load_crop(CROPS[0])[None]
    assert infer.probs(model, crop, 3.0).max() < infer.probs(model, crop, 1.0).max()


def test_model_recognises_most_fixtures(model):
    crops = np.stack([load_crop(p) for p in CROPS])
    pred = [infer.CLASSES[i] for i in infer.probs(model, crops, 1.0).argmax(axis=1)]
    truth = [p.stem.rsplit("_", 1)[0] for p in CROPS]
    assert sum(a == b for a, b in zip(pred, truth, strict=True)) >= len(CROPS) // 2


def test_confident_prediction_passes():
    assert calibrate.unsure_reason(_p(soiling=0.9, ok=0.1), TH) is None


def test_risk_class_needs_stricter_threshold():
    assert calibrate.unsure_reason(_p(soiling=0.65, other=0.35), TH) is None
    assert "sub pragul de" in calibrate.unsure_reason(_p(hot_cell=0.65, other=0.35), TH)


def test_ok_with_risk_mass_goes_to_queue():
    assert "risc" in calibrate.unsure_reason(_p(ok=0.8, hot_cell=0.1, diode_substring=0.1), TH)
    assert calibrate.unsure_reason(_p(ok=0.8, soiling=0.2), TH) is None


def test_reads_thresholds_written_by_ml_calibrate():
    th = calibrate.load_thresholds()
    assert set(th["min_conf"]) == set(infer.CLASSES)
    assert 0.5 < calibrate.load_temperature() < 3  # 0.76: label smoothing makes the ensemble modest
    # hot_cell has no threshold that keeps 95% precision, so it always goes to the engineer.
    assert calibrate.unsure_reason(_p(hot_cell=0.99, ok=0.01), th) == (
        "hot_cell merge mereu la inginer (încredere 99%)"
    )
    assert calibrate.unsure_reason(_p(ok=0.99, soiling=0.01), th) is None


def test_predictions_build_schema():
    [pred] = calibrate.predictions(_p(hot_cell=0.5, multi_hot=0.5)[None], 1.3, TH)
    assert pred.cls in ("hot_cell", "multi_hot")
    assert pred.unsure and pred.unsure_reason and pred.temperature == 1.3


def test_files_override_defaults(tmp_path):
    assert calibrate.load_temperature(tmp_path / "missing.json") == calibrate.DEFAULT_TEMPERATURE
    assert calibrate.load_thresholds(tmp_path / "missing.json") == TH
    (tmp_path / "t.json").write_text(json.dumps({"temperature": 1.7}))
    assert calibrate.load_temperature(tmp_path / "t.json") == 1.7
    (tmp_path / "th.json").write_text(json.dumps({**TH, "max_risk_prob_ok": 0.3}))
    assert calibrate.load_thresholds(tmp_path / "th.json")["max_risk_prob_ok"] == 0.3


def test_analyse_endpoint_uses_model():
    with TestClient(app) as client:
        crop = CROPS[0].read_bytes()
        res = client.post("/api/analyse", files={"file": ("c.jpg", crop, "image/jpeg")})
        assert res.status_code == 200, res.text
        body = res.json()
        assert abs(sum(body["probs"].values()) - 1) < 1e-3
        assert body["temperature"] == app.state.temperature
        bad = client.post("/api/analyse", files={"file": ("x.png", b"nope", "image/png")})
        assert bad.status_code == 422
        big = client.post("/api/analyse", files={"file": ("f.jpg", _jpg(48, 80), "image/jpeg")})
        assert big.status_code == 422


def _jpg(w: int, h: int) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("L", (w, h), 128).save(buf, format="JPEG")
    return buf.getvalue()


def test_each_prediction_carries_its_class_threshold():
    th = calibrate.load_thresholds()
    probs = np.stack([_p(hot_cell=0.99, ok=0.01), _p(ok=0.99, soiling=0.01)])
    [hot, ok] = calibrate.predictions(probs, 1.0, th)
    assert hot.threshold == th["min_conf"]["hot_cell"] > 1  # always to the engineer
    assert ok.threshold == th["min_conf"]["ok"] and not ok.unsure
