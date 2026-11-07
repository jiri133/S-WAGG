"""Grad-CAM (spec §3.5): torch weights match ONNX, diode heat falls on its 1/3 band, cache."""

import io
from pathlib import Path

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services.baseline.features import load_crop
from app.services.explain import gradcam
from app.services.pipeline import infer

CROPS = sorted((Path(__file__).parent / "fixtures" / "crops").glob("*.jpg"))
DIODE = next(p for p in CROPS if p.name.startswith("diode_substring"))
BAND = 8  # one third of the 24 px module width


@pytest.fixture(scope="module")
def model():
    return gradcam.load_model()


def test_torch_weights_match_onnx(model):
    """Same weights: ONNX = best.pt logits, plus the flip TTA and class bias (ticket 32)."""
    x = np.stack([load_crop(p) for p in CROPS]).astype(np.float32)[:, None] / 255
    onnx = infer.load_model().run(None, {"crop": x})[0]
    t = torch.from_numpy(x)
    with torch.no_grad():
        if infer.META.get("tta") == "probs":
            views = [t, t.flip(-1), t.flip(-2), t.flip(-1).flip(-2)]
            pt = torch.stack([torch.softmax(model(v), -1) for v in views]).mean(0).log().numpy()
        else:
            pt = model(t).numpy()
    pt = pt + np.array([infer.META.get("class_bias", {}).get(c, 0.0) for c in infer.CLASSES])
    assert np.abs(onnx - pt).max() < 1e-4


def test_diode_heat_falls_on_its_third(model):
    crop = load_crop(DIODE)
    cam = gradcam.heatmap(model, crop, "diode_substring")
    assert cam.shape == crop.shape and cam.min() >= 0 and cam.max() == pytest.approx(1)
    band = int(np.convolve(crop.mean(0), np.ones(BAND), "valid").argmax())  # hottest third
    heat = cam.mean(0)
    assert band <= heat.argmax() < band + BAND
    assert heat[band : band + BAND].sum() / heat.sum() > 0.4  # uniform would be 1/3


def test_overlay_is_rgb_png_of_crop_size(model):
    crop = load_crop(DIODE)
    img = Image.open(io.BytesIO(gradcam.overlay_png(crop, gradcam.heatmap(model, crop, "ok"))))
    assert img.format == "PNG" and img.mode == "RGB" and img.size == (24, 40)


def test_gradcam_endpoint_is_cached_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(gradcam, "CACHE", tmp_path)
    with TestClient(app) as client:
        res = client.get("/api/findings/F-033/gradcam.png")  # scenario 1's sure diode
        assert res.status_code == 200 and res.headers["content-type"] == "image/png"
        [cached] = tmp_path.iterdir()  # keyed by crop and class: finding ids repeat
        assert cached.read_bytes() == res.content
        cached.write_bytes(b"from-cache")
        assert client.get("/api/findings/F-033/gradcam.png").content == b"from-cache"
        assert client.get("/api/findings/nope/gradcam.png").status_code == 404
