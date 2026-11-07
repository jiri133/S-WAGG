"""Indexul de cazuri similare: un rând 512-d de normă 1 per crop din train, în ordinea din CSV."""

import csv

import numpy as np
import pytest

import build_index
import train

pytestmark = pytest.mark.skipif(
    not (train.ROOT / "data" / "raptor" / "InfraredSolarModules" / "images").exists()
    or not (build_index.OUT_DIR / "best.pt").exists(),
    reason="rulează întâi: uv run --project ml python ml/data.py",
)


def test_build_writes_unit_embeddings_and_rows(tmp_path):
    build_index.build(out_dir=tmp_path, limit=16)
    e = np.load(tmp_path / "embeddings.npy")
    with (tmp_path / "embeddings.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert e.shape == (16, 512) and e.dtype == np.float16 and len(rows) == 16
    np.testing.assert_allclose(np.linalg.norm(e.astype(np.float32), axis=1), 1, rtol=1e-2)
    assert {r["cls"] for r in rows} <= set(train.CLASSES)
