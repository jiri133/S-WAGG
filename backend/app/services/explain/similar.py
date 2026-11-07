"""Three similar train cases per finding (spec §3.5 point 3).

The finding's crop is embedded with the Grad-CAM network (512-d avgpool output, L2-normalised)
and compared by cosine against `artifacts/embeddings.npy`, built by `ml/build_index.py` over the
whole train set. The train crops are read from `data/` and sent as data: URLs, so the §9
contract needs no new endpoint. Without the index or the images, findings get no similar cases.
"""

import base64
import csv
import logging
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from app.schemas import SimilarCase
from app.services.explain.gradcam import Net, load_model
from app.services.findings import png
from app.services.pipeline.infer import ARTIFACTS

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[4]  # repo root: the index paths are relative to it


def embed(model: Net, crops: np.ndarray) -> np.ndarray:
    """(n, 40, 24) gray crops, pixels 0–255 → (n, 512) float32 rows of norm 1."""
    out = []
    hook = model.backbone.avgpool.register_forward_hook(lambda _m, _i, o: out.append(o))
    try:
        with torch.no_grad():
            model(torch.from_numpy(crops.astype(np.float32) / 255)[:, None])
    finally:
        hook.remove()
    e = out[0].flatten(1).numpy()
    return e / np.linalg.norm(e, axis=1, keepdims=True).clip(1e-8)


@lru_cache
def load_index(path: Path = ARTIFACTS / "embeddings.npy") -> tuple[np.ndarray, list[dict]] | None:
    """(embeddings float32, one {image_id, cls, path} row each), or None if not built."""
    rows_path = path.with_suffix(".csv")
    if not path.exists() or not rows_path.exists():
        log.warning("%s missing, no similar cases. Build: uv run --project ml python "
                    "ml/build_index.py", path)
        return None
    with rows_path.open(encoding="utf-8") as f:
        return np.load(path).astype(np.float32), list(csv.DictReader(f))


@lru_cache(maxsize=1024)
def crop_url(path: str) -> str:
    img = np.asarray(Image.open(ROOT / path).convert("L"))
    return "data:image/png;base64," + base64.b64encode(png(img)).decode()


def cases(crops: np.ndarray, k: int = 3) -> list[list[SimilarCase]]:
    """The k nearest train crops of each crop, nearest first; distance = 1 − cosine."""
    index = load_index()
    if index is None or not len(crops):
        return [[] for _ in crops]
    vectors, rows = index
    try:
        sims = embed(load_model(), crops) @ vectors.T
        top = np.argsort(-sims, axis=1)[:, :k]
        return [
            [
                SimilarCase(
                    id=f"raptor-{rows[j]['image_id']}",
                    cls=rows[j]["cls"],
                    crop_url=crop_url(rows[j]["path"]),
                    distance=round(float(1 - s[j]), 4),
                )
                for j in t
            ]
            for s, t in zip(sims, top, strict=True)
        ]
    except FileNotFoundError as e:  # the index is there but the train images are not
        log.warning("similar cases skipped: %s", e)
        return [[] for _ in crops]
