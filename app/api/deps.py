from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings
from app.services.embedding_service import EmbeddingService
from app.services.face_service import FaceService
from app.services.odoo_service import OdooService


def verify_register_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Guards POST /register. Without this, anyone reaching the service could
    enroll a face under any employee_id. No-op if REGISTER_API_KEY is unset
    (local dev only - must be set before exposing this service publicly).
    """
    if settings.register_api_key and x_api_key != settings.register_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key")


def get_face_service(request: Request) -> FaceService:
    return request.app.state.face_service


def get_embedding_service(request: Request) -> EmbeddingService:
    return request.app.state.embedding_service


def get_odoo_service(request: Request) -> OdooService:
    return request.app.state.odoo_service


def get_liveness_service(request: Request):
    """Returns the LivenessService, or None when LIVENESS_MODE=off."""
    return getattr(request.app.state, "liveness_service", None)
