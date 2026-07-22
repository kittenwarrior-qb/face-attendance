import base64

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.deps import get_embedding_service, get_odoo_service, verify_register_api_key
from app.config import Settings, get_settings
from app.schemas.face import AdminEmployeesResponse, RegisteredEmployee
from app.services.embedding_service import EmbeddingService
from app.services.odoo_service import OdooService
from app.utils.exceptions import OdooServiceError
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


@router.delete("/employees/{employee_id}")
async def delete_employee(
    employee_id: str,
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> dict[str, bool]:
    embedding_service.unregister(employee_id)
    logger.info("Admin removed face registration for employee_id=%s", employee_id)
    return {"success": True}
