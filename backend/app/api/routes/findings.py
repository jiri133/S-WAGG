from fastapi import APIRouter, HTTPException, Response, UploadFile

from app.schemas import Finding, Prediction, ReviewIn
from app.services import mock_data
from app.services.decision import workorders

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
    _get(finding_id)
    return Response(mock_data.gray_png(value=150), media_type="image/png")


@router.get("/findings/{finding_id}/gradcam.png", response_class=Response, responses=PNG)
def finding_gradcam(finding_id: str) -> Response:
    _get(finding_id)
    return Response(mock_data.gray_png(value=200), media_type="image/png")


@router.post("/analyse")
def analyse_crop(file: UploadFile) -> Prediction:
    """One 24×40 crop (PNG upload) → Prediction."""
    return mock_data.findings()[0].prediction
