import hashlib

import numpy as np
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlmodel import Session

from app.api.deps import SessionDep
from app.models import FindingRow
from app.schemas import Finding, Prediction, ReviewIn
from app.services import findings as results
from app.services.decision import workorders
from app.services.explain import gradcam
from app.services.pipeline import calibrate, infer

router = APIRouter(tags=["findings"])

PNG = {200: {"content": {"image/png": {}}}}


def _get(session: Session, finding_id: str) -> FindingRow:
    if found := results.row(session, finding_id):
        return found
    raise HTTPException(404, f"finding {finding_id} not found")


@router.get("/missions/{mission_id}/findings")
def list_findings(mission_id: str, session: SessionDep) -> list[Finding]:
    return workorders.prioritised(results.for_mission(session, mission_id))


@router.post("/findings/{finding_id}/review")
def review_finding(finding_id: str, review: ReviewIn, session: SessionDep) -> Finding:
    """Stores the decision; work orders are rebuilt from it on the next read."""
    return results.review(session, _get(session, finding_id), review)


@router.get("/findings/{finding_id}/crop.png", response_class=Response, responses=PNG)
def finding_crop(finding_id: str, session: SessionDep) -> Response:
    """The 24×40 gray crop the model classified."""
    return Response(_get(session, finding_id).crop, media_type="image/png")


@router.get("/findings/{finding_id}/gradcam.png", response_class=Response, responses=PNG)
def finding_gradcam(finding_id: str, session: SessionDep) -> Response:
    """Grad-CAM of the predicted class over the crop; computed once, then read from disk."""
    found = _get(session, finding_id)
    crop, cls = results.crop(found), found.data["prediction"]["cls"]
    key = hashlib.sha1(crop.tobytes() + cls.encode()).hexdigest()[:16]  # ids repeat
    return Response(gradcam.gradcam_png(key, crop, cls), media_type="image/png")


@router.post("/analyse")
def analyse_crop(file: UploadFile, request: Request) -> Prediction:
    """One 24×40 gray crop (PNG/JPG upload) → Prediction from the model."""
    try:
        crop = np.asarray(Image.open(file.file).convert("L"))
    except UnidentifiedImageError:
        raise HTTPException(422, "file is not an image") from None
    if crop.shape != (40, 24):
        raise HTTPException(422, f"crop must be 24×40 px, got {crop.shape[1]}×{crop.shape[0]}")
    s = request.app.state
    probs = infer.probs(s.model, crop[None], s.temperature)
    return calibrate.predictions(probs, s.temperature, s.thresholds)[0]
