"""Fixed mock data with the final API shape (DESIGN_SPEC §9).

Lets React work before the real simulator, pipeline and decision layer exist.
Each later ticket replaces one of these builders with the real service.
"""

import io
import struct
import zlib
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from app.schemas import (
    Alert,
    Evidence,
    Finding,
    Prediction,
    ReviewIn,
    SimilarCase,
    WorkOrder,
)
from app.services.decision import workorders
from app.services.sim.park import park

MOCK_TS = "2026-11-07T10:00:00Z"
SAMPLE_CROPS = Path(__file__).resolve().parents[2] / "artifacts" / "sample_crops"
CLASSES = (
    "ok",
    "hot_cell",
    "multi_hot",
    "diode_substring",
    "module_offline",
    "soiling",
    "shadow_vegetation",
    "other",
)


# module, model class, baseline class, apparent ΔT K, unsure
_FINDINGS = [
    ("B1-R2-T3-M07", "hot_cell", "hot_cell", 22.4, False),
    ("B1-R4-T1-M03", "diode_substring", "multi_hot", 9.8, False),
    ("B2-R1-T2-M11", "module_offline", "module_offline", 3.1, False),
    ("B2-R3-T4-M05", "multi_hot", "hot_cell", 12.6, True),
    ("B2-R5-T1-M09", "soiling", "ok", 2.2, False),
]
MOCK_MONTH = 11  # month of MOCK_TS, picks the PVGIS daily yield
# Engineer reviews, in memory until the mission state / SQLite ticket replaces this.
_reviews: dict[str, ReviewIn] = {}


def _finding(i: int, row: tuple) -> Finding:
    module_id, cls, base, dt, unsure = row
    fid = f"F-{i:03d}"
    # 0.01 on every other class, the rest on ok: the model hesitates between a fault and ok.
    top = 0.55 if unsure else 0.93
    probs = {c: 0.01 for c in CLASSES}
    probs["ok"] = round(1 - top - 0.01 * (len(CLASSES) - 2), 2)
    probs[cls] = top
    table = module_id.rsplit("-", 1)[0]
    prediction = Prediction(
        cls=cls,
        probs=probs,
        temperature=1.42,
        unsure=unsure,
        unsure_reason="probabilitate sub prag pe clasă de risc" if unsure else None,
    )
    fields = workorders.finding_fields(prediction, dt, MOCK_MONTH)
    rule = fields.pop("rule_applied")
    return Finding(
        id=fid,
        module_id=module_id,
        prediction=prediction,
        baseline_cls=base,
        **fields,
        evidence=Evidence(
            frame_ids=[f"FR-{table}-P1", f"FR-{table}-P2"],
            crop_url=f"/api/findings/{fid}/crop.png",
            gradcam_url=f"/api/findings/{fid}/gradcam.png",
            delta_t_k=dt,
            pattern="punct fierbinte izolat" if cls == "hot_cell" else "pattern mock",
            seen_in_both_passes=True,
            similar=[
                SimilarCase(
                    id=f"raptor-{1000 + i * 3 + k}",
                    cls=cls,
                    crop_url=f"/api/findings/{fid}/crop.png",
                    distance=round(0.1 + 0.05 * k, 2),
                )
                for k in range(3)
            ],
            rule_applied=rule,
        ),
    )


@lru_cache
def _detected() -> list[Finding]:
    return [_finding(i, row) for i, row in enumerate(_FINDINGS, start=1)]


def findings() -> list[Finding]:
    """Detected findings with the engineer's reviews applied."""
    return [
        f.model_copy(update={"review": r.decision, "review_note": r.note})
        if (r := _reviews.get(f.id))
        else f
        for f in _detected()
    ]


def review(finding_id: str, decision: ReviewIn) -> None:
    _reviews[finding_id] = decision


def work_orders() -> list[WorkOrder]:
    return workorders.work_orders(findings(), park(), MOCK_TS)


def alerts() -> list[Alert]:
    return [
        Alert(
            id="AL-001",
            finding_id="F-001",
            level="critical",
            message="Hot cell cu ΔT 22,4 K pe B1-R2-T3-M07 (≥ 20 K)",
            raised_at=MOCK_TS,
        )
    ]


def crop(finding: Finding) -> np.ndarray:
    """(40, 24) gray Raptor crop of the finding's class, until the simulator gives real ones."""
    return np.asarray(Image.open(SAMPLE_CROPS / f"{finding.prediction.cls}.jpg").convert("L"))


def png(image: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(image).save(buf, format="PNG")
    return buf.getvalue()


@lru_cache
def gray_png(width: int = 24, height: int = 40, value: int = 128) -> bytes:
    """A flat 8-bit grayscale PNG, built with the stdlib only."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\x00" + bytes([value]) * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
