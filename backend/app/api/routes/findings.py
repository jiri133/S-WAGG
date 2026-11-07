from fastapi import APIRouter, HTTPException, Response, UploadFile

from app.schemas import Finding, Prediction, ReviewIn
from app.services import mock_data

router = APIRouter(tags=["findings"])

PNG = {200: {"content": {"image/png": {}}}}


def _get(finding_id: str) -> Finding:
    for f in mock_data.findings():
        if f.id == finding_id:
            return f
    raise HTTPException(404, f"finding {finding_id} not found")


@router.get("/missions/{mission_id}/findings")
def list_findings(mission_id: str) -> list[Finding]:
    return sorted(mock_data.findings(), key=lambda f: f.score, reverse=True)


@router.post("/findings/{finding_id}/review")
def review_finding(finding_id: str, review: ReviewIn) -> Finding:
    return _get(finding_id).model_copy(
        update={"review": review.decision, "review_note": review.note}
    )


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
