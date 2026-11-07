"""Indexul pentru „cazuri similare” (spec §3.5 punctul 3).

Embedding-ul 512-d din stratul penultim (avgpool) al lui best.pt, L2-normalizat, pentru fiecare
crop din ml/splits/train.csv. Scrie backend/artifacts/embeddings.npy (float16, un rând per crop)
și embeddings.csv (image_id, cls, path: ce crop e pe fiecare rând).

Rulează din rădăcina repo-ului:  uv run --project ml python ml/build_index.py
"""

import csv
from pathlib import Path

import numpy as np
import torch
from torch import nn

from train import ROOT, SPLITS_DIR, Net, load_split

OUT_DIR = ROOT / "backend" / "artifacts"


def load_embedder(ckpt: Path) -> Net:
    """best.pt fără stratul `fc`: crop (N, 1, 40, 24) în [0, 1] → (N, 512)."""
    net = Net(pretrained=False)
    net.load_state_dict(torch.load(ckpt, map_location="cpu", weights_only=True)["state_dict"])
    net.backbone.fc = nn.Identity()
    return net.eval()


def embed(net: Net, x: torch.Tensor, bs: int = 512) -> np.ndarray:
    """(N, 1, 40, 24) în [0, 1] → (N, 512) float32, fiecare rând de normă 1."""
    with torch.no_grad():
        e = torch.cat([net(x[i : i + bs]) for i in range(0, len(x), bs)]).numpy()
    return e / np.linalg.norm(e, axis=1, keepdims=True).clip(1e-8)


def build(ckpt: Path = OUT_DIR / "best.pt", out_dir: Path = OUT_DIR, limit: int | None = None):
    with (SPLITS_DIR / "train.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[::max(1, len(rows) // limit)][:limit]  # același eșantion ca load_split
    x, _ = load_split("train", limit)
    np.save(out_dir / "embeddings.npy", embed(load_embedder(ckpt), x).astype(np.float16))
    with (out_dir / "embeddings.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image_id", "cls", "path"])
        w.writerows([r["image_id"], r["class"], r["path"]] for r in rows)
    size = (out_dir / "embeddings.npy").stat().st_size / 1e6
    print(f"{len(rows)} crop-uri → {out_dir / 'embeddings.npy'} ({size:.1f} MB)")


if __name__ == "__main__":
    build()
