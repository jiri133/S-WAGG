"""CNN mic antrenat de la zero, ca ablație (spec §3.3 punctul 4): al patrulea rând din evaluate.py.

Același split train, aceleași augmentări, echilibrare și selecție pe macro-F1 pe val ca ResNet18
(bucla din train.py), dar fără pre-antrenare, fără redimensionare și cu ~40× mai puțini parametri.
Exportă backend/artifacts/small_cnn.onnx, cu aceeași intrare și ieșire ca model.onnx, pe care
nu îl atinge. Merge pe CPU în câteva minute:

    uv run --project ml python ml/train_small.py
"""

import sys
from pathlib import Path

import torch
from torch import nn

import train

OUT_ONNX = train.ROOT / "backend" / "artifacts" / "small_cnn.onnx"
DEFAULTS = ["--epochs", "15", "--lr", "3e-3", "--out", str(train.ROOT / "ml" / "runs" / "small")]


def block(cin: int, cout: int) -> nn.Sequential:
    """Două conv 3×3 cu BatchNorm și ReLU, apoi max-pool 2× (înjumătățește înălțimea și lățimea)."""
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(),
        nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(),
        nn.MaxPool2d(2),
    )


class SmallNet(nn.Module):
    """Crop gri (N, 1, 40, 24) în [0, 1] → logits pe cele 8 clase; 40×24 → 5×3 după 3 blocuri."""

    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(block(1, 32), block(32, 64), block(64, 128))
        self.head = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(0.3),
                                  nn.Linear(128, len(train.CLASSES)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x))


def export(ckpt: Path, onnx_path: Path) -> Path:
    model = SmallNet()
    model.load_state_dict(torch.load(ckpt, map_location="cpu")["state_dict"])
    torch.onnx.export(
        model.eval(), torch.zeros(1, 1, *train.CROP_HW), onnx_path, dynamo=False,
        opset_version=17, input_names=["crop"], output_names=["logits"],
        dynamic_axes={"crop": {0: "batch"}, "logits": {0: "batch"}},
    )
    return onnx_path


def main(argv: list[str]) -> dict:
    args = train.parse_args(DEFAULTS + argv)  # argumentele date în linia de comandă câștigă
    torch.manual_seed(train.SEED)
    result = train.train(args, SmallNet())
    export(Path(args.out) / "best.pt", OUT_ONNX)
    print(f"{OUT_ONNX} ({OUT_ONNX.stat().st_size / 1e6:.2f} MB)")
    return result


if __name__ == "__main__":
    main(sys.argv[1:])
