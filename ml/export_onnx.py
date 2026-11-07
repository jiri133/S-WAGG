"""Exportă best.pt (din train.py) în backend/artifacts/model.onnx + model_meta.json.

Intrarea ONNX e crop-ul brut, fără altă preprocesare: (N, 1, 40, 24) float32 = pixel / 255.
Redimensionarea la 64×96 și normalizarea ImageNet sunt în graf (vezi `Net` din train.py).

Rulează din rădăcina repo-ului:
    uv run --project ml python ml/export_onnx.py --ckpt ml/runs/best.pt
"""

import argparse
import json
from pathlib import Path

import torch

from train import CLASSES, CROP_HW, INPUT_HW, MEAN, ROOT, STD, Net


def export(ckpt: Path, out_dir: Path) -> Path:
    state = torch.load(ckpt, map_location="cpu")
    model = Net(pretrained=False)
    model.load_state_dict(state["state_dict"])
    model.eval()
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
        "output": "logits, fără softmax; temperature scaling se aplică separat",
        "classes": CLASSES,
        "epoch": state["epoch"],
        "val_macro_f1": state["val_macro_f1"],
    }
    (out_dir / "model_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    print(f"{onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB), val macro-F1 "
          f"{state['val_macro_f1']:.4f}")
    return onnx_path


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ckpt", default=str(ROOT / "ml" / "runs" / "best.pt"))
    p.add_argument("--out-dir", default=str(ROOT / "backend" / "artifacts"))
    a = p.parse_args()
    export(Path(a.ckpt), Path(a.out_dir))
