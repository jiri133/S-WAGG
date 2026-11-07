"""CNN-ul mic de ablație: forma ieșirii, un pas de antrenare, exportul ONNX = PyTorch."""

import numpy as np
import onnxruntime as ort
import torch
from torch import nn

import train
import train_small


def test_small_net_shape_and_size():
    model = train_small.SmallNet()
    assert model(torch.rand(3, 1, *train.CROP_HW)).shape == (3, len(train.CLASSES))
    assert sum(p.numel() for p in model.parameters()) < 500_000  # ResNet18 are ~11 M


def test_one_training_step_lowers_loss_on_a_tiny_batch():
    torch.manual_seed(0)
    model, x = train_small.SmallNet(), torch.rand(8, 1, *train.CROP_HW)
    y = torch.arange(8) % len(train.CLASSES)
    opt, loss_fn = torch.optim.AdamW(model.parameters(), lr=1e-2), nn.CrossEntropyLoss()
    losses = []
    for _ in range(5):
        loss = loss_fn(model(x), y)
        opt.zero_grad()
        loss.backward()
        opt.step()
        losses.append(loss.item())
    assert losses[-1] < losses[0]


def test_export_matches_pytorch(tmp_path):
    model = train_small.SmallNet().eval()
    torch.save({"state_dict": model.state_dict()}, tmp_path / "best.pt")
    onnx_path = train_small.export(tmp_path / "best.pt", tmp_path / "small_cnn.onnx")

    x = torch.rand(2, 1, *train.CROP_HW)
    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    logits = sess.run(["logits"], {"crop": x.numpy()})[0]
    with torch.no_grad():
        np.testing.assert_allclose(logits, model(x).numpy(), rtol=1e-3, atol=1e-4)
