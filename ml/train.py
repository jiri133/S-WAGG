"""ResNet18 pe crop-urile IR Raptor (spec §3.3).

Crop gri 24×40 → 64×96 (W×H), replicat pe 3 canale, normalizare ImageNet. Preprocesarea e
în model (`Net`), deci ONNX-ul primește direct crop-ul brut (N, 1, 40, 24) în [0, 1].
Class weights + oversampling ușor, augmentări flip H/V, ±luminozitate, zgomot (fără rotație).
Selecția pe macro-F1 pe val. Split-ul test nu e citit aici (doar evaluate.py).

Rulează din rădăcina repo-ului, după `uv run --project ml python ml/data.py`:
    uv run --project ml python ml/train.py --device cpu --epochs 1 --limit 256
Pe Kaggle: python ml/train.py --device cuda
"""

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from sklearn.metrics import confusion_matrix, f1_score
from torch import nn
from torchvision.models import ResNet18_Weights, resnet18

ROOT = Path(__file__).resolve().parent.parent
SPLITS_DIR = ROOT / "ml" / "splits"
CLASSES = [
    "ok", "hot_cell", "multi_hot", "diode_substring",
    "module_offline", "soiling", "shadow_vegetation", "other",
]
CROP_HW = (40, 24)  # crop-ul Raptor: 24 lățime × 40 înălțime
INPUT_HW = (96, 64)  # intrarea ResNet: 64 lățime × 96 înălțime
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
SEED = 42


class Net(nn.Module):
    """Crop gri (N, 1, 40, 24) în [0, 1] → logits pe cele 8 clase."""

    def __init__(self, pretrained: bool = True):
        super().__init__()
        self.backbone = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1 if pretrained else None)
        self.backbone.fc = nn.Linear(self.backbone.fc.in_features, len(CLASSES))
        self.register_buffer("mean", torch.tensor(MEAN).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(STD).view(1, 3, 1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.interpolate(x, size=INPUT_HW, mode="bilinear", align_corners=False)
        x = (x.expand(-1, 3, -1, -1) - self.mean) / self.std
        return self.backbone(x)


def load_split(name: str, limit: int | None = None) -> tuple[torch.Tensor, torch.Tensor]:
    """Citește crop-urile unui split în memorie: (N, 1, 40, 24) float în [0, 1] și etichetele."""
    with (SPLITS_DIR / f"{name}.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[::max(1, len(rows) // limit)][:limit]  # eșantion uniform, are toate clasele
    x = np.stack([np.asarray(Image.open(ROOT / r["path"]).convert("L")) for r in rows])
    y = [CLASSES.index(r["class"]) for r in rows]
    return torch.from_numpy(x).float().div(255).unsqueeze(1), torch.tensor(y)


def augment(x: torch.Tensor) -> torch.Tensor:
    """Flip H/V, ±luminozitate, zgomot gaussian. Fără rotație de 90° (crop-ul nu e pătrat)."""
    n = x.shape[0]
    flip_w = torch.rand(n, device=x.device) < 0.5
    flip_h = torch.rand(n, device=x.device) < 0.5
    x = torch.where(flip_w.view(-1, 1, 1, 1), x.flip(-1), x)
    x = torch.where(flip_h.view(-1, 1, 1, 1), x.flip(-2), x)
    x = x + (torch.rand(n, 1, 1, 1, device=x.device) - 0.5) * 0.2
    x = x + torch.randn_like(x) * 0.02
    return x.clamp(0, 1)


def balance(y: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Jumătate din echilibrare prin oversampling, jumătate prin loss (ambele ∝ 1/√n_clasă)."""
    counts = torch.bincount(y, minlength=len(CLASSES)).float().clamp(min=1)
    class_w = counts.rsqrt()
    class_w = class_w / class_w[counts > 0].mean()
    return class_w, class_w[y]


@torch.no_grad()
def predict(model: nn.Module, x: torch.Tensor, device: str, bs: int = 512) -> np.ndarray:
    model.eval()
    out = [model(x[i:i + bs].to(device)).argmax(1).cpu() for i in range(0, len(x), bs)]
    return torch.cat(out).numpy()


def report(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    labels = list(range(len(CLASSES)))
    per_class = f1_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    return {
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "accuracy": float((y_true == y_pred).mean()),
        "f1_per_class": dict(zip(CLASSES, map(float, per_class), strict=True)),
        "support": {CLASSES[k]: v for k, v in sorted(Counter(y_true.tolist()).items())},
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def train(args: argparse.Namespace, model: nn.Module | None = None) -> dict:
    """Antrenează `model` (implicit ResNet18 `Net`) și salvează best.pt după macro-F1 pe val."""
    torch.manual_seed(SEED)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    x_tr, y_tr = load_split("train", args.limit)
    x_va, y_va = load_split("val", args.limit)
    class_w, sample_w = balance(y_tr)
    print(f"train {len(y_tr)}, val {len(y_va)}, device {args.device}")

    model = (model or Net(pretrained=not args.no_pretrained)).to(args.device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    steps = args.epochs * ((len(y_tr) + args.batch_size - 1) // args.batch_size)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps)
    loss_fn = nn.CrossEntropyLoss(weight=class_w.to(args.device))

    best, history = None, []
    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        model.train()
        idx = torch.multinomial(sample_w, len(y_tr), replacement=True)
        total = 0.0
        for i in range(0, len(idx), args.batch_size):
            b = idx[i:i + args.batch_size]
            xb, yb = augment(x_tr[b].to(args.device)), y_tr[b].to(args.device)
            loss = loss_fn(model(xb), yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            total += loss.item() * len(b)
        rep = report(y_va.numpy(), predict(model, x_va, args.device))
        history.append({"epoch": epoch, "loss": total / len(idx), "val_macro_f1": rep["macro_f1"]})
        print(f"epoca {epoch}: loss {total / len(idx):.4f}, val macro-F1 {rep['macro_f1']:.4f}, "
              f"{time.time() - t0:.0f} s")
        if best is None or rep["macro_f1"] > best["macro_f1"]:
            best = {"epoch": epoch, **rep}
            torch.save({"state_dict": model.state_dict(), "classes": CLASSES, "epoch": epoch,
                        "val_macro_f1": rep["macro_f1"]}, out / "best.pt")

    result = {"best": best, "history": history, "args": vars(args)}
    (out / "val_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"cel mai bun: epoca {best['epoch']}, val macro-F1 {best['macro_f1']:.4f} → {out}")
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--device", choices=["cuda", "cpu"], default="cpu")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--out", default=str(ROOT / "ml" / "runs"))
    p.add_argument("--limit", type=int, default=None, help="max crop-uri per split (smoke test)")
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--no-pretrained", action="store_true", help="fără greutăți ImageNet (teste)")
    return p.parse_args(argv)


if __name__ == "__main__":
    train(parse_args())
