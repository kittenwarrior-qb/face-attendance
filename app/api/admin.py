import base64

import cv2
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.deps import get_embedding_service, get_face_service, get_odoo_service, verify_register_api_key
from app.config import Settings, get_settings
from app.schemas.face import AdminEmployeesResponse, RegisteredEmployee
from app.services.embedding_service import EmbeddingService
from app.services.face_service import FaceService
from app.services.odoo_service import OdooService
from app.utils.exceptions import OdooServiceError
from app.utils.image_utils import decode_base64_image, encode_image_to_jpeg
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Same X-API-Key gate as /register - this page can enroll/remove faces, so it
# needs the same protection as enrollment itself.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_register_api_key)])


@router.get("/employees", response_model=AdminEmployeesResponse)
async def list_employees(
    odoo_service: OdooService = Depends(get_odoo_service),
    settings: Settings = Depends(get_settings),
) -> AdminEmployeesResponse:
    raw = odoo_service.list_registered_employees()
    employees = sorted((RegisteredEmployee(**item) for item in raw), key=lambda e: e.employee_name)
    return AdminEmployeesResponse(
        liveness_mode=settings.liveness_mode,
        liveness_threshold=settings.liveness_threshold,
        liveness_require_sequence=settings.liveness_require_sequence,
        liveness_min_frames=settings.liveness_min_frames,
        total_registered=len(employees),
        employees=employees,
    )


@router.get("/employees/{employee_id}/avatar")
async def get_employee_avatar(
    employee_id: str,
    odoo_service: OdooService = Depends(get_odoo_service),
) -> Response:
    """Small thumbnail (Odoo's auto-resized image_128) for the admin table."""
    try:
        avatar_b64 = odoo_service.get_employee_avatar(employee_id, field="image_128")
    except OdooServiceError:
        # Barcode doesn't resolve to any hr.employee - same "nothing to show"
        # outcome from the admin table's point of view as a missing avatar.
        avatar_b64 = None
    if not avatar_b64:
        raise HTTPException(status_code=404, detail="No avatar on file for this employee")
    return Response(content=base64.b64decode(avatar_b64), media_type="image/jpeg")


@router.get("/employees/{employee_id}/device-image")
async def get_employee_device_image(
    employee_id: str,
    face_service: FaceService = Depends(get_face_service),
    odoo_service: OdooService = Depends(get_odoo_service),
) -> dict[str, object]:
    """Return a small portrait containing only the dominant face.

    The ZKTeco firmware analyses the uploaded photo itself and rejects photos
    that contain several detectable faces. Odoo's normal avatar crop is not
    face-aware, so use the same trusted-avatar detector used during enrollment.
    """
    avatar_b64 = odoo_service.get_employee_avatar(employee_id, field="image_1920")
    if not avatar_b64:
        raise HTTPException(status_code=404, detail="No avatar on file for this employee")

    image = decode_base64_image(avatar_b64)
    _embedding, (x, y, width, height) = face_service.extract_largest_face(image)
    image_height, image_width = image.shape[:2]

    # Keep hair/chin context while preserving the portrait ratio expected by
    # the device. Clamp the crop because avatars may already be tightly framed.
    crop_width = min(image_width, max(width * 2.0, height * 1.35))
    crop_height = min(image_height, max(int(crop_width * 1.5), height * 2.4))
    crop_width = min(crop_width, crop_height / 1.5)
    center_x = x + width / 2
    center_y = y + height * 0.48
    left = int(round(center_x - crop_width / 2))
    top = int(round(center_y - crop_height * 0.42))
    left = max(0, min(left, image_width - int(crop_width)))
    top = max(0, min(top, image_height - int(crop_height)))
    cropped = image[top : top + int(crop_height), left : left + int(crop_width)]
    cropped = cv2.resize(cropped, (200, 300), interpolation=cv2.INTER_AREA)
    encoded = base64.b64encode(encode_image_to_jpeg(cropped, quality=82)).decode("ascii")
    return {"success": True, "image": encoded, "width": 200, "height": 300}


@router.delete("/employees/{employee_id}")
async def delete_employee(
    employee_id: str,
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> dict[str, bool]:
    embedding_service.unregister(employee_id)
    logger.info("Admin removed face registration for employee_id=%s", employee_id)
    return {"success": True}
