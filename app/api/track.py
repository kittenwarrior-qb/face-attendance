from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_face_service
from app.schemas.face import TrackResponse
from app.services.face_service import FaceService
from app.utils.image_utils import decode_upload_image

router = APIRouter(tags=["face"])


@router.post("/track", response_model=TrackResponse)
async def track_face(
    file: UploadFile = File(..., description="Camera frame containing at most one face"),
    face_service: FaceService = Depends(get_face_service),
) -> TrackResponse:
    """Return the InsightFace bounding box for realtime client overlays.

    This endpoint deliberately performs detection only: it does not run
    recognition, liveness, or create an Odoo attendance record.
    """
    image = await decode_upload_image(file)
    _, bbox = face_service.extract_single_face(image)
    return TrackResponse(success=True, bbox=list(bbox))
