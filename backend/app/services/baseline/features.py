"""Intensity features of one 24×40 thermal crop (gray levels 0–255, not °C).

The module is 6×10 cells of 4×4 px, wired as 3 substrings of 2 cell columns
(one bypass diode each), so a substring is a vertical band 1/3 of the width.
The crop has a dark 1–2 px frame, so everything except the band layout is
measured on the inner area.
"""

import numpy as np

BORDER = 2  # px of frame dropped before measuring
HOT = 20  # gray levels above the median that count as "hot"
WARM = 8  # gray levels above the median for a "warm" 4×4 cell
COLD = 15  # gray levels below the median that count as "cold"
MIN_BLOB = 2  # px; smaller hot specks are noise
BANDS = [(4, 8), (8, 16), (16, 20)]  # substring columns, minus the darker edge ramp

FEATURE_NAMES = [
    "median",  # absolute level; an offline module is warm all over
    "std",
    "peak",  # max minus median
    "hot_frac",  # share of pixels above median + HOT
    "n_blobs",  # separate hot spots
    "largest_blob",  # px in the biggest hot spot
    "n_warm_cells",  # 4×4 cells whose mean is above median + WARM
    "n_hot_cells",  # 4×4 cells whose mean is above median + HOT
    "band_contrast",  # warmest substring band minus the other two
    "band_cover",  # share of the warmest band above the other bands' mean
    "band_spread",  # warmest minus coolest substring band
    "uniform_frac",  # share of pixels within ±WARM of the median
    "cold_frac",  # share of pixels below median - COLD
    "bottom_delta",  # mean of the bottom 2 cell rows minus median
    "top_delta",  # mean of the top 2 cell rows minus median
    "row_spread",  # warmest minus coolest cell row (shadows, soiling at an edge)
    "frame_contrast",  # median minus the outer 1 px ring (module warmer than around it)
]


def load_crop(path) -> np.ndarray:
    """A crop file as a float array of shape (40, 24)."""
    from PIL import Image

    return np.asarray(Image.open(path).convert("L"), dtype=np.float64)


def count_blobs(mask: np.ndarray) -> list[int]:
    """Sizes of the 4-connected components of a boolean mask."""
    labels = np.where(mask, np.arange(mask.size).reshape(mask.shape) + 1, 0)
    while True:
        grown = labels.copy()
        grown[1:] = np.maximum(grown[1:], labels[:-1])
        grown[:-1] = np.maximum(grown[:-1], labels[1:])
        grown[:, 1:] = np.maximum(grown[:, 1:], labels[:, :-1])
        grown[:, :-1] = np.maximum(grown[:, :-1], labels[:, 1:])
        grown = np.where(mask, grown, 0)
        if np.array_equal(grown, labels):
            break
        labels = grown
    _, sizes = np.unique(labels[mask], return_counts=True)
    return sizes.tolist()


def extract(crop: np.ndarray) -> dict[str, float]:
    """All FEATURE_NAMES for one (40, 24) gray crop."""
    crop = np.asarray(crop, dtype=np.float64)
    inner = crop[BORDER:-BORDER, BORDER:-BORDER]
    med = float(np.median(inner))

    blobs = [s for s in count_blobs(inner > med + HOT) if s >= MIN_BLOB]
    cells = crop.reshape(10, 4, 6, 4).mean(axis=(1, 3))[1:-1, :]  # drop framed top/bottom rows

    rows = crop[BORDER:-BORDER]
    band_means = [rows[:, a:b].mean() for a, b in BANDS]
    worst = int(np.argmax(band_means))
    others = [m for i, m in enumerate(band_means) if i != worst]
    a, b = BANDS[worst]
    ring = np.concatenate([crop[[0, -1]].ravel(), crop[:, [0, -1]].ravel()])

    return {
        "median": med,
        "std": float(inner.std()),
        "peak": float(inner.max() - med),
        "hot_frac": float((inner > med + HOT).mean()),
        "n_blobs": float(len(blobs)),
        "largest_blob": float(max(blobs, default=0)),
        "n_warm_cells": float((cells > med + WARM).sum()),
        "n_hot_cells": float((cells > med + HOT).sum()),
        "band_contrast": float(band_means[worst] - np.mean(others)),
        "band_cover": float((rows[:, a:b] > np.mean(others)).mean()),
        "band_spread": float(max(band_means) - min(band_means)),
        "uniform_frac": float((np.abs(inner - med) <= WARM).mean()),
        "cold_frac": float((inner < med - COLD).mean()),
        "bottom_delta": float(crop[-8 - BORDER : -BORDER, BORDER:-BORDER].mean() - med),
        "top_delta": float(crop[BORDER : 8 + BORDER, BORDER:-BORDER].mean() - med),
        "row_spread": float(np.ptp(cells.mean(axis=1))),
        "frame_contrast": float(med - ring.mean()),
    }


def vector(crop: np.ndarray) -> np.ndarray:
    """extract() as a vector in FEATURE_NAMES order, for the Random Forest."""
    f = extract(crop)
    return np.array([f[n] for n in FEATURE_NAMES])
