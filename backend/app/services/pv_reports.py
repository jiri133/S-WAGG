"""Read the PV forecast model metrics written by ``RL/scripts/train_pv.py``.

``train_pv.py`` writes ``RL/artifacts/models/pv/metrics.json``: overall MAE, RMSE
and bias per split, the persistence baseline and the per-lead breakdown. The
Evaluare page shows them next to the classifier and battery results.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import settings
from app.schemas.pv_eval import PvEvalReport, PvLeadMetrics, PvSplitMetrics

SPLIT_ORDER = ("train", "val", "test")


def metrics_path() -> Path:
    return settings.rl_root / "artifacts" / "models" / "pv" / "metrics.json"


def load_metrics(path: Path | None = None) -> PvEvalReport:
    """Load the training metrics; raises ``FileNotFoundError`` if not generated yet."""
    source = path or metrics_path()
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw_splits = raw.get("splits") or {}
    return PvEvalReport(
        model=str(raw.get("model") or "—"),
        version=str(raw.get("version") or ""),
        trained_at_utc=raw.get("trained_at_utc"),
        farm=(raw.get("farm") or {}).get("name"),
        rows=raw.get("rows"),
        n_features=len(raw.get("features") or []),
        splits=[
            _split(name, raw_splits[name])
            for name in SPLIT_ORDER
            if name in raw_splits
        ],
    )


def _split(name: str, data: dict) -> PvSplitMetrics:
    overall = data.get("overall") or {}
    persistence = data.get("persistence") or {}
    leads = [
        PvLeadMetrics(
            lead=lead,
            n=int(values.get("n") or 0),
            mae=values.get("mae"),
            rmse=values.get("rmse"),
            bias=values.get("bias"),
        )
        for lead, values in (data.get("by_lead") or {}).items()
        if values.get("n")
    ]
    return PvSplitMetrics(
        split=name,
        n=int(overall.get("n") or 0),
        mae=overall.get("mae"),
        rmse=overall.get("rmse"),
        bias=overall.get("bias"),
        persistence_mae=persistence.get("mae"),
        by_lead=leads,
    )
