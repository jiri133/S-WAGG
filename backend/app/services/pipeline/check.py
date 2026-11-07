"""Step 1 (DESIGN_SPEC §5): reject frames that cannot be analysed and tables left without one.

A frame is rejected for: irradiance below 600 W/m², wind above 8 m/s, no timestamp or position,
non-physical temperatures, an RGB frame (`channels != 1` or `radiometric=false`) or a frame with
no module grid (bare ground). A table whose delivered frames all fail the check is
`not_inspected`; its reason is the union of the frames' problems, and the caller proposes a
refly.

Frames are checked once, then `not_inspected_tables` works on the `check_ok`/`problems` fields
filled by `frame`.
"""

from collections import defaultdict
from collections.abc import Iterable

import numpy as np

from app.schemas import FrameMeta
from app.services.sim.artefacts import GROUND_C

MIN_IRRADIANCE_WM2 = 600.0
MAX_WIND_MS = 8.0
T_MIN_C, T_MAX_C = -40.0, 150.0
FLAT_STD_C = 1.0  # a ground patch is flat to within sensor noise
GROUND_TOL_C = 1.0  # and sits at the ground temperature of §4


def problems(meta: FrameMeta, img: np.ndarray | None) -> list[str]:
    """Reasons to reject one frame; empty when it is usable."""
    out = []
    if meta.irradiance_wm2 < MIN_IRRADIANCE_WM2:
        out.append(f"iradianță {meta.irradiance_wm2:.0f} W/m² < {MIN_IRRADIANCE_WM2:.0f}")
    if meta.wind_ms > MAX_WIND_MS:
        out.append(f"vânt {meta.wind_ms:.1f} m/s > {MAX_WIND_MS:.0f}")
    if not meta.timestamp or (meta.lat == 0 and meta.lon == 0):
        out.append("fără timp sau poziție")
    if meta.channels != 1 or not meta.radiometric:
        out.append(f"nu e radiometric: {meta.channels} canale, radiometric={meta.radiometric}")
    out += _image_problems(img)
    return out


def frame(meta: FrameMeta, img: np.ndarray | None) -> FrameMeta:
    """The frame metadata with `check_ok` and `problems` filled in."""
    probs = problems(meta, img)
    return meta.model_copy(update={"check_ok": not probs, "problems": probs})


def not_inspected_tables(frames: Iterable[FrameMeta], table_ids: Iterable[str]) -> dict[str, str]:
    """Tables with no usable frame → the reason each becomes `not_inspected` (§5 step 1)."""
    by_table: dict[str, list[FrameMeta]] = defaultdict(list)
    for f in frames:
        by_table[f.table].append(f)
    out = {}
    for table in table_ids:
        delivered = by_table[table]
        if any(f.check_ok for f in delivered):
            continue
        reasons = sorted({p for f in delivered for p in f.problems})
        out[table] = "; ".join(reasons) if reasons else "niciun cadru livrat"
    return out


def _image_problems(img: np.ndarray | None) -> list[str]:
    if img is None:
        return ["cadru lipsă"]
    if img.ndim != 2:
        return [f"imaginea are {img.shape[-1]} canale, nu e termică"]
    if not np.isfinite(img).all():
        return ["temperaturi invalide (NaN)"]
    lo, hi = float(img.min()), float(img.max())
    out = []
    if lo < T_MIN_C or hi > T_MAX_C:
        out.append(f"temperaturi invalide ({lo:.0f}…{hi:.0f} °C)")
    if is_ground(img):
        out.append("nicio grilă de module")
    return out


def is_ground(patch: np.ndarray) -> bool:
    """Bare ground: flat to within sensor noise and at the ground temperature of §4."""
    return float(patch.std()) < FLAT_STD_C and abs(float(patch.mean()) - GROUND_C) < GROUND_TOL_C
