"""Exportă best.pt (din train.py) în backend/artifacts/model.onnx + model_meta.json.

Intrarea ONNX e crop-ul brut, fără altă preprocesare: (N, 1, 40, 24) float32 = pixel / 255.
Redimensionarea la 64×96 și normalizarea ImageNet sunt în graf (vezi `Net` din train.py).
Opțional (tichetul 32, ales pe val de ml/boost.py): TTA cu flip-uri și un bias pe clase, tot
în graf, cu aceeași intrare și ieșire.

Rulează din rădăcina repo-ului:
    uv run --project ml python ml/export_onnx.py --ckpt ml/runs/best.pt
"""

import argparse
import json
from pathlib import Path

import torch
from torch import nn

from train import CLASSES, CROP_HW, INPUT_HW, MEAN, ROOT, STD, Net

TTA_MODES = ("logits", "probs")


class Boosted(nn.Module):
    """Net + TTA pe 4 flip-uri (media logits sau log din media softmax) + bias pe clase."""

    def __init__(self, net: nn.Module, bias: list[float], tta: str | None):
        super().__init__()
        assert tta in (None, *TTA_MODES), tta
        self.net, self.tta = net, tta
        self.register_buffer("bias", torch.tensor(bias, dtype=torch.float32))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.tta is None:
            return self.net(x) + self.bias
        n = x.shape[0]
        views = torch.cat([x, x.flip(-1), x.flip(-2), x.flip(-1).flip(-2)])
        z = self.net(views).reshape(4, n, -1)
        z = z.mean(0) if self.tta == "logits" else torch.log(torch.softmax(z, -1).mean(0))
        return z + self.bias


def load_net(ckpt: Path) -> tuple[Net, dict]:
    state = torch.load(ckpt, map_location="cpu")
    model = Net(pretrained=False)
    model.load_state_dict(state["state_dict"])
    return model.eval(), state


def export(ckpt: Path, out_dir: Path, tta: str | None = None, bias: list[float] | None = None,
           val_macro_f1: float | None = None) -> Path:
    model, state = load_net(ckpt)
    output = "logits, fără softmax; temperature scaling se aplică separat"
    if tta is not None or bias is not None:
        bias = bias if bias is not None else [0.0] * len(CLASSES)
        model = Boosted(model, bias, tta).eval()
        output = (f"logits (TTA {tta or 'nu'} pe 4 flip-uri + bias pe clase), fără softmax; "
                  "temperature scaling se aplică separat")
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = out_dir / "model.onnx"
    torch.onnx.export(
        model, torch.zeros(1, 1, *CROP_HW), onnx_path, dynamo=False, opset_version=17,
        input_names=["crop"], output_names=["logits"],
        dynamic_axes={"crop": {0: "batch"}, "logits": {0: "batch"}},
    )
    meta = {
        "input_name": "crop",
        "input_shape": ["batch", 1, *CROP_HW],
        "input_dtype": "float32",
        "input_scale": "pixel / 255 (crop gri 8 biți, 24 lățime × 40 înălțime)",
        "in_graph_preprocessing": {
            "resize_hw": list(INPUT_HW), "channels": 3, "mean": MEAN, "std": STD,
        },
        "output_name": "logits",
        "output": output,
        "classes": CLASSES,
        "epoch": state["epoch"],
        "val_macro_f1": state["val_macro_f1"] if val_macro_f1 is None else val_macro_f1,
    }
    if isinstance(model, Boosted):
        meta |= {"tta": tta, "class_bias": dict(zip(CLASSES, bias, strict=True)),
                 "val_macro_f1_base": state["val_macro_f1"]}
    (out_dir / "model_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    print(f"{onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB), val macro-F1 "
          f"{meta['val_macro_f1']:.4f}")
    return onnx_path


class Ensemble(nn.Module):
    """Several Nets (ticket 36): mean of the softmax over the 4 flips and the members, log,
    plus the class bias. Same input and output as a single Net."""

    def __init__(self, nets: list[nn.Module], bias: list[float]):
        super().__init__()
        self.nets = nn.ModuleList(nets)
        self.register_buffer("bias", torch.tensor(bias, dtype=torch.float32))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        n = x.shape[0]
        views = torch.cat([x, x.flip(-1), x.flip(-2), x.flip(-1).flip(-2)])
        p = torch.stack([torch.softmax(net(views), -1) for net in self.nets]).mean(0)
        return torch.log(p.reshape(4, n, -1).mean(0)) + self.bias


def export_ensemble(ckpts: list[Path], out_dir: Path, bias: list[float],
                    val_macro_f1: float) -> Path:
    """model.onnx + model_meta.json for an ensemble of `ckpts` (same interface as `export`)."""
    model = Ensemble([load_net(c)[0] for c in ckpts], bias).eval()
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = out_dir / "model.onnx"
    torch.onnx.export(
        model, torch.zeros(1, 1, *CROP_HW), onnx_path, dynamo=False, opset_version=17,
        input_names=["crop"], output_names=["logits"],
        dynamic_axes={"crop": {0: "batch"}, "logits": {0: "batch"}},
    )
    meta = {
        "input_name": "crop",
        "input_shape": ["batch", 1, *CROP_HW],
        "input_dtype": "float32",
        "input_scale": "pixel / 255 (crop gri 8 biți, 24 lățime × 40 înălțime)",
        "in_graph_preprocessing": {
            "resize_hw": list(INPUT_HW), "channels": 3, "mean": MEAN, "std": STD,
        },
        "output_name": "logits",
        "output": (f"logits: ansamblu de {len(ckpts)} ResNet18, media softmax pe 4 flip-uri și "
                   "pe membri, log, + bias pe clase; temperature scaling se aplică separat"),
        "classes": CLASSES,
        "members": [c.name for c in ckpts],
        "tta": "probs",
        "class_bias": dict(zip(CLASSES, bias, strict=True)),
        "val_macro_f1": val_macro_f1,
    }
    (out_dir / "model_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    print(f"{onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB), val macro-F1 {val_macro_f1:.4f}")
    return onnx_path


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ckpt", default=str(ROOT / "ml" / "runs" / "best.pt"))
    p.add_argument("--out-dir", default=str(ROOT / "backend" / "artifacts"))
    a = p.parse_args()
    export(Path(a.ckpt), Path(a.out_dir))
