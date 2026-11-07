"""Thermal frames composed from Raptor test crops (DESIGN_SPEC §4).

Every module slot (24×40 px) gets a crop from `ml/splits/test.csv` of the module's planted class
("ok" for healthy modules), converted to apparent temperature:

    T = T_base + (pix − median_ok) × K_PER_LEVEL

where `median_ok` is the median gray level of the "ok" crops. Frames are never stored: the same
MissionSettings always regenerate the same frames. Without the Raptor images on disk (CI,
Docker) synthetic crops with the same patterns stand in.
"""

import csv
import io
import logging
import math
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import get_args

import numpy as np
from PIL import Image

from app.schemas import FaultClass, FrameMeta, MissionSettings
from app.services.sim import artefacts
from app.services.sim.park import (
    MODULE_H_M,
    MODULE_W_M,
    SLOT_H,
    SLOT_W,
    TABLE_COLS,
    park,
    tables,
)

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[4]  # repo root; crop paths in the CSV are relative to it
TEST_CSV = ROOT / "ml" / "splits" / "test.csv"
CLASSES: tuple[FaultClass, ...] = get_args(FaultClass)
FAULTS = CLASSES[1:]  # every class but "ok"
K_PER_LEVEL = 0.15  # K per gray level (§4)
START = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)
FRAME_INTERVAL_S = 4
LAT0, LON0 = 44.4268, 26.1025  # the park's top-left corner, near Bucharest
M_PER_DEG_LAT = 111_320.0
THUMB_MIN_C, THUMB_MAX_C = 10.0, 70.0  # gray scale of the thumbnails


@lru_cache
def crops() -> dict[FaultClass, np.ndarray]:
    """Test-split crops per class, read-only uint8 (n, 40, 24). Synthetic if not on disk."""
    rows = []
    if TEST_CSV.exists():
        with TEST_CSV.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    if not rows or not (ROOT / rows[0]["path"]).exists():
        log.warning(
            "Raptor crops not found, using synthetic ones. "
            "Get the real ones with: uv run --project ml python ml/data.py"
        )
        out = _synthetic_crops()
    else:
        by_cls: dict[FaultClass, list[np.ndarray]] = {c: [] for c in CLASSES}
        for r in rows:
            with Image.open(ROOT / r["path"]) as im:
                by_cls[r["class"]].append(np.asarray(im.convert("L")))
        out = {c: np.stack(v) for c, v in by_cls.items()}
    for a in out.values():
        a.setflags(write=False)  # shared by every mission: nobody may change a crop in place
    return out


@lru_cache
def median_ok() -> float:
    """Median gray level of the healthy crops; it maps to T_base."""
    return float(np.median(crops()["ok"]))


def to_temperature(crop: np.ndarray, t_base: float) -> np.ndarray:
    """Gray levels → apparent temperature in °C (§4)."""
    return t_base + (crop.astype(np.float32) - median_ok()) * K_PER_LEVEL


def to_gray(temp: np.ndarray, t_base: float) -> np.ndarray:
    """Apparent temperature → gray levels, the inverse of `to_temperature` for the model."""
    return median_ok() + (temp.astype(np.float32) - t_base) / K_PER_LEVEL


def truth(settings: MissionSettings) -> dict[str, FaultClass]:
    """Ground truth: the planted class of every module; `n_faults` of them are not "ok"."""
    modules = park()
    rng = np.random.default_rng([settings.seed, 1])
    order = rng.permutation(len(modules))
    kinds = rng.integers(len(FAULTS), size=len(modules))
    out: dict[str, FaultClass] = {m.id: "ok" for m in modules}
    for i in range(settings.n_faults):
        out[modules[order[i]].id] = FAULTS[kinds[i]]
    return out


def module_crops(settings: MissionSettings) -> dict[str, np.ndarray]:
    """The crop in each module's slot, drawn from the module's planted class."""
    lib, planted = crops(), truth(settings)
    u = np.random.default_rng([settings.seed, 2]).random(len(park()))
    out = {}
    for i, m in enumerate(park()):
        pool = lib[planted[m.id]]
        out[m.id] = pool[int(u[i] * len(pool))]
    return out


def frames(settings: MissionSettings) -> list[FrameMeta]:
    """Metadata of every delivered frame, in flight order; lost frames are absent.

    `check_ok`, `problems` and `gps_offset_detected` are pipeline results (ticket 17), so the
    simulator leaves them neutral.
    """
    return [_meta(f) for f in artefacts.plan(settings) if not f["lost"]]


def frame_image(settings: MissionSettings, frame_id: str) -> np.ndarray | None:
    """Regenerate one frame: °C float32 (80, 144), or uint8 RGB (80, 144, 3).

    None if the frame does not exist or was lost.
    """
    for f in artefacts.plan(settings):
        if f["id"] == frame_id and not f["lost"]:
            return _render(settings, f)
    return None


def png(img: np.ndarray) -> bytes:
    """PNG of a frame: RGB as is, temperatures as gray from 10 °C (black) to 70 °C (white)."""
    if img.ndim == 2:
        scale = 255 / (THUMB_MAX_C - THUMB_MIN_C)
        img = np.clip((img - THUMB_MIN_C) * scale, 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return buf.getvalue()


def _render(settings: MissionSettings, f: dict) -> np.ndarray:
    if f["inject"] == "rgb":
        return artefacts.rgb_frame()
    img = artefacts.ground(np.random.default_rng([settings.seed, 4, f["index"]]))
    if f["inject"] == "no_panels":
        return img
    slots, t_base = module_crops(settings), artefacts.t_base(f["irradiance_wm2"])
    for m in tables()[f["table"]]:
        half, col = divmod(m.pos - 1, TABLE_COLS)
        c = col - f["gps"]  # a GPS offset shifts the table; the freed slots keep the ground
        if 0 <= c < TABLE_COLS:
            img[half * SLOT_H : (half + 1) * SLOT_H, c * SLOT_W : (c + 1) * SLOT_W] = (
                to_temperature(slots[m.id], t_base)
            )
    return artefacts.with_glare(img, f["glare"]) if f["glare"] else img


def _meta(f: dict) -> FrameMeta:
    first = tables()[f["table"]][0]  # top-left module of the table
    x = first.x_m + TABLE_COLS * MODULE_W_M / 2 + (f["pass_no"] - 1.5)  # passes 1 m apart
    y = first.y_m + MODULE_H_M  # between the 2 rows of modules
    ts = START + timedelta(seconds=FRAME_INTERVAL_S * f["index"])
    rgb = f["inject"] == "rgb"
    return FrameMeta(
        id=f["id"],
        table=f["table"],
        pass_no=f["pass_no"],
        file=f"{f['id']}.png",
        timestamp=ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        lat=round(LAT0 - y / M_PER_DEG_LAT, 7),
        lon=round(LON0 + x / (M_PER_DEG_LAT * math.cos(math.radians(LAT0))), 7),
        irradiance_wm2=f["irradiance_wm2"],
        wind_ms=f["wind_ms"],
        channels=3 if rgb else 1,
        radiometric=not rgb,
        check_ok=True,
        problems=[],
        gps_offset_detected=0,
        thumb_url=f"/api/frames/{f['id']}/thumb.png",
    )


def _synthetic_crops(per_class: int = 16) -> dict[FaultClass, np.ndarray]:
    """Stand-in crops with the §3.3 patterns, used only when the Raptor images are missing."""
    rng = np.random.default_rng(0)
    out = {}
    for cls in CLASSES:
        batch = []
        for _ in range(per_class):
            img = rng.normal(160.0, 4.0, (SLOT_H, SLOT_W))
            cells = img.reshape(10, 4, 6, 4)  # view: [cell row, px, cell column, px]
            if cls == "hot_cell":
                cells[rng.integers(10), :, rng.integers(6)] += rng.uniform(60, 90)
            elif cls == "multi_hot":
                for _ in range(rng.integers(2, 5)):
                    cells[rng.integers(10), :, rng.integers(6)] += rng.uniform(50, 80)
            elif cls == "diode_substring":  # one of 3 substrings, 2 cell columns wide
                s = rng.integers(3)
                img[:, 8 * s : 8 * s + 8] += rng.uniform(35, 50)
            elif cls == "module_offline":
                img += rng.uniform(30, 40)
            elif cls == "soiling":  # dirt along the lower edge
                img[-8:] += rng.uniform(15, 25)
            elif cls == "shadow_vegetation":  # vegetation patch in a lower corner
                img[-12:, : rng.integers(8, 25)] += rng.uniform(25, 40)
            elif cls == "other":  # a crack across the module
                r = np.arange(SLOT_H)
                img[r, (r * rng.uniform(0.3, 0.6)).astype(int)] += 50
            batch.append(np.clip(img, 0, 255).astype(np.uint8))
        out[cls] = np.stack(batch)
    return out
