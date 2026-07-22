from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import (
    get_embedding_service,
    get_face_service,
    get_liveness_service,
    get_odoo_service,
    verify_register_api_key,
)
from app.config import Settings, get_settings
from app.schemas.face import RegisterResponse
from app.services.embedding_service import EmbeddingService
from app.services.face_service import FaceService
from app.services.odoo_service import OdooService
from app.utils.exceptions import InvalidImageError, SpoofDetectedError
from app.utils.image_utils import decode_base64_image, decode_upload_image, encode_image_to_jpeg
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["face"])


@router.post("/register", response_model=RegisterResponse, dependencies=[Depends(verify_register_api_key)])
async def register_face(
    employee_id: str = Form(..., description="Employee code (matches Odoo hr.employee.barcode)"),
    file: UploadFile = File(..., description="Photo containing exactly one face"),
    face_service: FaceService = Depends(get_face_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    liveness_service=Depends(get_liveness_service),
    settings: Settings = Depends(get_settings),
) -> RegisterResponse:
    image = await decode_upload_image(file)
    embedding, bbox = face_service.extract_single_face(image)
    if liveness_service is not None:
        liveness = liveness_service.check(image, bbox)
        if not liveness.is_real and settings.liveness_mode == "enforce":
            raise SpoofDetectedError(
                f"Registration image looks like a photo/screen (real_score={liveness.real_score:.3f})"
            )

    image_bytes = encode_image_to_jpeg(image) if settings.store_original_image else None
    employee_name = embedding_service.register(employee_id, embedding, image_bytes)
    logger.info("Registered face for employee_id=%s (%s)", employee_id, employee_name)

    return RegisterResponse(success=True, employee_id=employee_id, employee_name=employee_name)


@router.post(
    "/register/odoo-avatar",
    response_model=RegisterResponse,
    dependencies=[Depends(verify_register_api_key)],
)
async def register_face_from_odoo_avatar(
    employee_id: str = Form(..., description="Employee barcode in Odoo"),
    face_service: FaceService = Depends(get_face_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    odoo_service: OdooService = Depends(get_odoo_service),
) -> RegisterResponse:
    """Enroll from the trusted employee avatar already stored in Odoo.

    Liveness intentionally does not run here: the caller is authenticated with
    the registration key and the source image is Odoo master data. Live scans
    still go through the full anti-spoofing pipeline in /verify.
    """
    avatar = odoo_service.get_employee_avatar(employee_id)
    if not avatar:
        raise InvalidImageError("Employee has no avatar in Odoo")

    image = decode_base64_image(avatar)
    embedding, _bbox = face_service.extract_single_face(image)
    employee_name = embedding_service.register(employee_id, embedding, None)
    logger.info("Registered Odoo avatar for employee_id=%s (%s)", employee_id, employee_name)
    return RegisterResponse(success=True, employee_id=employee_id, employee_name=employee_name)


@router.post("/register/remove", dependencies=[Depends(verify_register_api_key)])
async def remove_registered_face(
    employee_id: str = Form(..., description="Previously registered employee barcode"),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> dict[str, bool]:
    embedding_service.unregister(employee_id)
    logger.info("Removed face registration for employee_id=%s", employee_id)
    return {"success": True}
