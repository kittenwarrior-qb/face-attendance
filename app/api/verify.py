from datetime import datetime, timezone

import cv2
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_embedding_service, get_face_service, get_odoo_service
from app.config import Settings, get_settings
from app.schemas.face import AttendanceResult, GPSPoint, VerifyResponse
from app.services.embedding_service import EmbeddingService
from app.services.face_service import FaceService
from app.services.odoo_service import OdooService
from app.utils.exceptions import OdooServiceError
from app.utils.image_utils import decode_upload_image
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["face"])


@router.post("/verify", response_model=VerifyResponse)
async def verify_face(
    file: UploadFile = File(..., description="Photo containing exactly one face"),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    db: Session = Depends(get_db),
    face_service: FaceService = Depends(get_face_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    odoo_service: OdooService = Depends(get_odoo_service),
    settings: Settings = Depends(get_settings),
) -> VerifyResponse:
    image = await decode_upload_image(file)
    embedding = face_service.extract_single_embedding(image)

    match = embedding_service.find_best_match(db, embedding)
    if match is None:
        logger.info("Verification failed: no match above threshold %.3f", settings.face_match_threshold)
        return VerifyResponse(success=False, message="Face not recognized")

    gps = GPSPoint(latitude=latitude, longitude=longitude) if latitude is not None and longitude is not None else None

    image_bytes = None
    if settings.odoo_attach_image:
        image_bytes = cv2.imencode(".jpg", image)[1].tobytes()

    try:
        attendance = odoo_service.create_attendance(
            employee_id=match.employee_id,
            timestamp=datetime.now(timezone.utc),
            latitude=latitude,
            longitude=longitude,
            image_bytes=image_bytes,
        )
    except OdooServiceError as exc:
        logger.error("Verified employee_id=%s but Odoo attendance failed: %s", match.employee_id, exc)
        return VerifyResponse(
            success=True,
            employee_id=match.employee_id,
            score=match.score,
            message=f"Face verified but attendance was not recorded: {exc}",
        )

    return VerifyResponse(
        success=True,
        employee_id=match.employee_id,
        score=match.score,
        attendance=AttendanceResult(
            action=attendance.action,
            odoo_attendance_id=attendance.odoo_attendance_id,
            timestamp=attendance.timestamp,
            gps=gps,
        ),
        message="Attendance recorded",
    )
