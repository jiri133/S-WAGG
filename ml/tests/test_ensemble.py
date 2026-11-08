"""Tichetul 36: ansamblul în numpy = `Ensemble` în PyTorch = model.onnx în ONNX Runtime."""

import json

import numpy as np
import onnxruntime as ort
import torch

import ensemble
import export_onnx
import train


def test_combine_of_identical_members_is_the_member():
    p = np.random.default_rng(0).dirichlet(np.ones(8), 20)
    assert np.allclose(ensemble.combine([p, p]), np.log(p))


def test_exported_ensemble_matches_numpy(tmp_path):
    torch.manual_seed(0)
    ckpts = []
    for i in range(2):
        net = train.Net(pretrained=False)
        path = tmp_path / f"m{i}.pt"
        torch.save({"state_dict": net.state_dict(), "epoch": 1, "val_macro_f1": 0.0}, path)
        ckpts.append(path)
    x = torch.rand(3, 1, 40, 24)
    bias = [0.0, 0.5, -0.5, 0.0, 1.0, 0.0, -1.0, 0.2]

    expected = ensemble.combine([ensemble.member_probs(c, x) for c in ckpts]) + np.array(bias)
    onnx = export_onnx.export_ensemble(ckpts, tmp_path, bias, val_macro_f1=0.5)
    got = ort.InferenceSession(str(onnx)).run(None, {"crop": x.numpy()})[0]
    assert got.shape == (3, 8)
    np.testing.assert_allclose(got, expected, atol=1e-4)

    meta = json.loads((tmp_path / "model_meta.json").read_text(encoding="utf-8"))
    assert meta["members"] == ["m0.pt", "m1.pt"] and meta["tta"] == "probs"
