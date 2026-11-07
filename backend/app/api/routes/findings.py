import numpy as np
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from PIL import Image, UnidentifiedImageError

from app.schemas import Finding, Prediction, ReviewIn
from app.services import mock_data
from app.services.decision import workorders
from app.services.explain import gradcam
from app.services.pipeline import calibrate, infer

router = APIRouter(tags=["findings"])

PNG = {200: {"content": {"image/png": {}}}}


def _get(finding_id: str) -> Finding:
    for f in mock_data.findings():
        if f.id == finding_id:
            return f
    raise HTTPException(404, f"finding {finding_id} not found")


@router.get("/missions/{mission_id}/findings")
def list_findings(mission_id: str) -> list[Finding]:
    return workorders.prioritised(mock_data.findings())


@router.post("/findings/{finding_id}/review")
def review_finding(finding_id: str, review: ReviewIn) -> Finding:
    """Stores the decision; work orders are rebuilt from it on the next read."""
    _get(finding_id)
    mock_data.review(finding_id, review)
    return _get(finding_id)


@router.get("/findings/{finding_id}/crop.png", response_class=Response, responses=PNG)
def finding_crop(finding_id: str) -> Response:
    return Response(mock_data.png(mock_data.crop(_get(finding_id))), media_type="image/png")


@router.get("/findings/{finding_id}/gradcam.png", response_class=Response, responses=PNG)
def finding_gradcam(finding_id: str) -> Response:
    """Grad-CAM of the predicted class over the crop; computed once, then read from disk."""
    f = _get(finding_id)
    png = gradcam.gradcam_png(f.id, mock_data.crop(f), f.prediction.cls)
    return Response(png, media_type="image/png")


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
