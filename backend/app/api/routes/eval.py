import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["eval"])

EVAL_JSON = Path(__file__).resolve().parents[4] / "reports" / "eval.json"


@router.get("/eval")
def get_eval() -> dict[str, Any]:
    """Serves reports/eval.json written by evaluate.py (§3.6)."""
    if not EVAL_JSON.exists():
        raise HTTPException(404, "reports/eval.json not generated yet; run evaluate.py")
    return json.loads(EVAL_JSON.read_text(encoding="utf-8"))
