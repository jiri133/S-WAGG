from pathlib import Path

import numpy as np
import pytest

from app.services.baseline.features import FEATURE_NAMES, count_blobs, extract, load_crop, vector
from app.services.baseline.rules_classifier import CLASSES, RULES, classify, load_thresholds

# One real Raptor crop per class (train split), named <class>_<image_id>.jpg.
CROPS = sorted((Path(__file__).parent / "fixtures" / "crops").glob("*.jpg"))


def flat_module(level: float = 150, frame: float = 140) -> np.ndarray:
    crop = np.full((40, 24), level)
    crop[0], crop[-1], crop[:, 0], crop[:, -1] = frame, frame, frame, frame
    return crop


def test_count_blobs_separates_spots():
    mask = np.zeros((6, 6), dtype=bool)
    mask[0, 0:2] = True
    mask[4:6, 4:6] = True
    assert sorted(count_blobs(mask)) == [2, 4]


def test_flat_module_has_nothing_hot():
    f = extract(flat_module())
    assert f["peak"] == 0 and f["n_blobs"] == 0 and f["hot_frac"] == 0
    assert f["uniform_frac"] == 1
    assert f["frame_contrast"] > 0


def test_one_hot_cell_is_one_blob():
    crop = flat_module()
    crop[12:16, 8:12] += 60
    f = extract(crop)
    assert f["n_blobs"] == 1 and f["largest_blob"] == 16
    assert f["n_hot_cells"] == 1 and f["peak"] == 60


def test_warm_substring_band():
    crop = flat_module()
    crop[2:-2, 16:22] += 25  # third substring warmer
    f = extract(crop)
    assert f["band_contrast"] == pytest.approx(25)
    assert f["band_cover"] == 1


def test_vector_follows_feature_names():
    crop = flat_module()
    assert vector(crop).tolist() == [extract(crop)[n] for n in FEATURE_NAMES]


def test_thresholds_cover_every_rule():
    keys = {key for _, conds in RULES for _, _, key in conds}
    assert keys == set(load_thresholds())
    assert {cls for cls, _ in RULES} | {"ok"} == set(CLASSES)


def test_flat_module_is_ok():
    assert classify(flat_module()) == "ok"


def test_uniform_module_much_warmer_than_frame_is_offline():
    assert classify(flat_module(level=200, frame=100)) == "module_offline"


def test_fixtures_have_one_crop_per_class():
    assert sorted(p.stem.rsplit("_", 1)[0] for p in CROPS) == sorted(CLASSES)


@pytest.mark.parametrize("path", CROPS, ids=lambda p: p.stem)
def test_real_crop(path):
    crop = load_crop(path)
    assert crop.shape == (40, 24)
    assert np.isfinite(vector(crop)).all()
    assert classify(crop) == path.stem.rsplit("_", 1)[0]
