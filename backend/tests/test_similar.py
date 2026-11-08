"""Similar cases (spec §3.5 point 3): embeddings, cosine top-3, empty without an index."""

import base64
import io
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services.baseline.features import load_crop
from app.services.explain import gradcam, similar
from app.services.pipeline import analyse

CROPS = sorted((Path(__file__).parent / "fixtures" / "crops").glob("*.jpg"))


def _real_index_available() -> bool:
    """The committed index points at Raptor crops; CI has no dataset, so those tests skip."""
    index = similar.load_index()
    return index is not None and (similar.ROOT / index[1][0]["path"]).exists()


@pytest.fixture
def fixture_index(monkeypatch):
    """An index of the 8 fixture crops, one per class, instead of the train set."""
    crops = np.stack([load_crop(p) for p in CROPS])
    rows = [
        {"image_id": p.stem.rsplit("_", 1)[1], "cls": p.stem.rsplit("_", 1)[0],
         "path": p.relative_to(similar.ROOT).as_posix()}
        for p in CROPS
    ]
    monkeypatch.setattr(similar, "load_index", lambda: (similar.embed(gradcam.load_model(),
                                                                       crops), rows))
    return crops, rows


def test_embeddings_are_512d_unit_rows():
    e = similar.embed(gradcam.load_model(), np.stack([load_crop(p) for p in CROPS]))
    assert e.shape == (len(CROPS), 512)
    np.testing.assert_allclose(np.linalg.norm(e, axis=1), 1, rtol=1e-5)


def test_nearest_case_is_the_crop_itself(fixture_index):
    crops, rows = fixture_index
    found = similar.cases(crops)
    assert [len(c) for c in found] == [3] * len(crops)
    for cs, row in zip(found, rows, strict=True):
        assert cs[0].id == f"raptor-{row['image_id']}" and cs[0].cls == row["cls"]
        assert cs[0].distance == pytest.approx(0, abs=1e-3)
        assert [c.distance for c in cs] == sorted(c.distance for c in cs)
        png = base64.b64decode(cs[0].crop_url.removeprefix("data:image/png;base64,"))
        assert np.array_equal(np.asarray(Image.open(io.BytesIO(png))), crops[rows.index(row)])


def test_no_index_means_no_similar_cases(monkeypatch, tmp_path):
    assert similar.load_index(tmp_path / "embeddings.npy") is None
    monkeypatch.setattr(similar, "load_index", lambda: None)
    assert similar.cases(np.stack([load_crop(CROPS[0])])) == [[]]


def test_findings_carry_three_similar_cases(fixture_index):
    crops, _ = fixture_index
    with TestClient(app) as client:
        res = client.get("/api/missions/M-0001/findings").json()
    f = analyse.Finding.model_validate(res[0])
    [(out, _)] = analyse.with_similar([(f, crops[0])])
    assert len(out.evidence.similar) == 3 and out.id == f.id
    assert analyse.with_similar([]) == []


@pytest.mark.skipif(not _real_index_available(), reason="real Raptor crops not on disk")
def test_train_crop_finds_itself_in_the_real_index():
    """ml/build_index.py and this service embed the same way."""
    _, rows = similar.load_index()
    picks = rows[:: len(rows) // 8][:8]
    found = similar.cases(np.stack([load_crop(similar.ROOT / r["path"]) for r in picks]))
    for cs, r in zip(found, picks, strict=True):
        assert cs[0].id == f"raptor-{r['image_id']}" and cs[0].distance < 1e-2


@pytest.mark.skipif(not _real_index_available(), reason="real Raptor crops not on disk")
def test_scenario_findings_have_similar_train_cases():
    with TestClient(app) as client:  # M-0001: scenario 1, analysed by conftest
        found = client.get("/api/missions/M-0001/findings").json()
    assert found and all(len(f["evidence"]["similar"]) == 3 for f in found)
    assert all(f["evidence"]["similar"][0]["crop_url"].startswith("data:image/png;base64,")
               for f in found)
