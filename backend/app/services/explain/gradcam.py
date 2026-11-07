"""Grad-CAM on the v1 ResNet18, PyTorch on CPU (spec §3.5).

Same weights as `model.onnx` (`artifacts/best.pt`); ONNX does the inference, this file only
explains it. The model loads on the first call, so the API starts fast.

Uses layer3, not layer4: on the 64×96 input layer4 is a 2×3 grid, too coarse to show a band one
third wide (on 250 val diode crops its band share is 0.33, same as uniform; layer3 gives 0.48).
Weights are gradient × activation per cell (the HiResCAM form of Grad-CAM).
"""

import io
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch import nn
from torchvision.models import resnet18

from app.services.pipeline.infer import ARTIFACTS, CLASSES, META

CACHE = Path(__file__).resolve().parents[3] / "cache" / "gradcam"
PRE = META["in_graph_preprocessing"]


class Net(nn.Module):
    """Copy of `ml/train.py:Net`: gray crop (N, 1, 40, 24) in [0, 1] → logits."""

    def __init__(self):
        super().__init__()
        self.backbone = resnet18(weights=None)
        self.backbone.fc = nn.Linear(self.backbone.fc.in_features, len(CLASSES))
        self.register_buffer("mean", torch.tensor(PRE["mean"]).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(PRE["std"]).view(1, 3, 1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.interpolate(x, size=PRE["resize_hw"], mode="bilinear", align_corners=False)
        x = (x.expand(-1, 3, -1, -1) - self.mean) / self.std
        return self.backbone(x)


@lru_cache
def load_model(path: Path = ARTIFACTS / "best.pt") -> Net:
    model = Net()
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True)["state_dict"])
    return model.eval()


def heatmap(model: Net, crop: np.ndarray, cls: str) -> np.ndarray:
    """(40, 24) gray crop, pixels 0–255 → (40, 24) Grad-CAM in [0, 1] for class `cls`."""
    acts = []
    hook = model.backbone.layer3.register_forward_hook(lambda _m, _i, out: acts.append(out))
    try:
        logits = model(torch.from_numpy(crop.astype(np.float32) / 255)[None, None])
    finally:
        hook.remove()
    (grads,) = torch.autograd.grad(logits[0, CLASSES.index(cls)], acts[0])
    cam = F.relu((grads * acts[0]).sum(1, keepdim=True))
    cam = F.interpolate(cam, size=crop.shape, mode="bilinear", align_corners=False)[0, 0]
    return (cam / cam.max().clamp_min(1e-8)).detach().numpy()


def overlay_png(crop: np.ndarray, cam: np.ndarray, alpha: float = 0.5) -> bytes:
    """Gray crop with a blue→red heatmap on top, as PNG bytes."""
    jet = np.clip(1.5 - np.abs(4 * cam[..., None] - np.array([3, 2, 1])), 0, 1)
    rgb = (1 - alpha) * crop[..., None] / 255 + alpha * jet
    buf = io.BytesIO()
    Image.fromarray((rgb * 255).astype(np.uint8)).save(buf, format="PNG")
    return buf.getvalue()


def gradcam_png(finding_id: str, crop: np.ndarray, cls: str) -> bytes:
    """Overlay PNG for one finding, cached on disk at `cache/gradcam/<id>.png`."""
    path = CACHE / f"{finding_id}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(overlay_png(crop, heatmap(load_model(), crop, cls)))
    return path.read_bytes()
