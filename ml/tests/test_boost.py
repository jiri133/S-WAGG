"""Tichetul 32: căutarea bias-ului, TTA în numpy și `Boosted` exportat în ONNX (date sintetice)."""

import json

import numpy as np
import onnxruntime as ort
import torch
from sklearn.metrics import f1_score

import boost
import export_onnx
import train

K = len(train.CLASSES)


def test_macro_f1_matches_sklearn():
    rng = np.random.default_rng(0)
    y, pred = rng.integers(0, K, 500), rng.integers(0, K, 500)
    expected = f1_score(y, pred, labels=list(range(K)), average="macro", zero_division=0)
    assert np.isclose(boost.macro_f1(y, pred), expected)


def test_search_bias_fixes_an_underpredicted_class():
    rng = np.random.default_rng(1)
    y = rng.integers(0, K, 3000)
    z = rng.normal(0, 1, (3000, K))
    z[np.arange(3000), y] += 2.0
    z[:, 3] -= 2.5  # clasa 3 e aproape niciodată prezisă
    bias, f = boost.search_bias(z, y)
    assert bias[0] == 0 and bias[3] > 1.5
    assert f > boost.macro_f1(y, z.argmax(1)) + 0.05
    assert np.isclose(f, boost.macro_f1(y, (z + bias).argmax(1)))


def test_tta_logits_is_mean_and_probs_averages_softmax():
    views = np.random.default_rng(2).normal(0, 2, (4, 10, K))
    assert np.allclose(boost.tta(views, "logits"), views.mean(0))
    soft = np.exp(views) / np.exp(views).sum(-1, keepdims=True)
    out = boost.tta(views, "probs")
    assert np.allclose(np.exp(out), soft.mean(0)) and np.allclose(np.exp(out).sum(1), 1)


def test_boosted_onnx_matches_numpy_and_is_flip_invariant(tmp_path):
    torch.manual_seed(0)
    net = train.Net(pretrained=False).eval()
    torch.save({"state_dict": net.state_dict(), "epoch": 1, "val_macro_f1": 0.5},
               tmp_path / "best.pt")
    bias = [0.0, -0.5, 0.3, 0.0, -1.0, 0.7, 0.0, 0.2]
    x = torch.rand(5, 1, *train.CROP_HW)

    path = export_onnx.export(tmp_path / "best.pt", tmp_path, tta="probs", bias=bias,
                              val_macro_f1=0.6)
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    assert inp.name == "crop" and inp.shape == ["batch", 1, 40, 24]
    assert sess.get_outputs()[0].name == "logits"
    z = sess.run(None, {"crop": x.numpy()})[0]

    expected = boost.tta(boost.view_logits(net, x), "probs") + np.array(bias)
    np.testing.assert_allclose(z, expected, rtol=1e-3, atol=1e-4)
    flipped = sess.run(None, {"crop": x.flip(-1).flip(-2).numpy()})[0]
    np.testing.assert_allclose(z, flipped, rtol=1e-3, atol=1e-4)

    meta = json.loads((tmp_path / "model_meta.json").read_text(encoding="utf-8"))
    assert meta["tta"] == "probs" and meta["class_bias"]["module_offline"] == -1.0
    assert meta["val_macro_f1"] == 0.6 and meta["val_macro_f1_base"] == 0.5
