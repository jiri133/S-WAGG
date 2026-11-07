"""Smoke: o epocă pe un subset → best.pt → model.onnx → ONNX Runtime pe CPU pe un crop real."""

import json

import numpy as np
import onnxruntime as ort
import pytest
import torch

import export_onnx
import train

pytestmark = pytest.mark.skipif(
    not (train.ROOT / "data" / "raptor" / "InfraredSolarModules" / "images").exists(),
    reason="rulează întâi: uv run --project ml python ml/data.py",
)


def test_augment_keeps_shape_and_range():
    x = torch.rand(8, 1, *train.CROP_HW)
    y = train.augment(x)
    assert y.shape == x.shape and y.min() >= 0 and y.max() <= 1


def test_train_export_onnxruntime(tmp_path):
    args = train.parse_args(["--epochs", "1", "--limit", "64", "--batch-size", "32",
                             "--no-pretrained", "--out", str(tmp_path)])
    result = train.train(args)
    assert 0 <= result["best"]["macro_f1"] <= 1
    assert (tmp_path / "best.pt").exists() and (tmp_path / "val_report.json").exists()

    onnx_path = export_onnx.export(tmp_path / "best.pt", tmp_path)
    meta = json.loads((tmp_path / "model_meta.json").read_text(encoding="utf-8"))
    assert meta["classes"] == train.CLASSES and meta["input_shape"][1:] == [1, 40, 24]

    x, _ = train.load_split("val", limit=1)
    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    logits = sess.run(None, {meta["input_name"]: x.numpy()})[0]
    assert logits.shape == (1, len(train.CLASSES))

    model = train.Net(pretrained=False)
    model.load_state_dict(torch.load(tmp_path / "best.pt")["state_dict"])
    with torch.no_grad():
        expected = model.eval()(x).numpy()
    np.testing.assert_allclose(logits, expected, rtol=1e-3, atol=1e-4)
