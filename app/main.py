from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import health, register, ui, verify
from app.config import get_settings
from app.database.base import Base
from app.database.session import engine
from app.repositories.face_repository import FaceRepository
from app.services.embedding_service import EmbeddingService
from app.services.face_service import FaceService
from app.services.odoo_service import OdooService
from app.utils.exceptions import (
    FaceAttendanceError,
    InvalidImageError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    OdooServiceError,
)
from app.utils.logger import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)

ERROR_STATUS_MAP: dict[type[FaceAttendanceError], int] = {
    InvalidImageError: 400,
    NoFaceDetectedError: 422,
    MultipleFacesDetectedError: 422,
    OdooServiceError: 502,
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Creating database tables if they do not exist...")
    Base.metadata.create_all(bind=engine)

    logger.info("Initializing services...")
    app.state.face_service = FaceService(settings)
    face_repository = FaceRepository()
    app.state.embedding_service = EmbeddingService(face_repository, settings.face_match_threshold)
    app.state.odoo_service = OdooService(settings)

    if not settings.register_api_key:
        logger.warning(
            "REGISTER_API_KEY is not set - POST /register is UNAUTHENTICATED. "
            "Set it before exposing this service on a public domain."
        )

    logger.info("Startup complete.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.app_name,
    description="Face recognition attendance service integrated with Odoo Attendance.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(register.router)
app.include_router(verify.router)
app.include_router(ui.router)


@app.exception_handler(FaceAttendanceError)
async def face_attendance_error_handler(request: Request, exc: FaceAttendanceError) -> JSONResponse:
    status_code = ERROR_STATUS_MAP.get(type(exc), 400)
    return JSONResponse(status_code=status_code, content={"success": False, "detail": str(exc)})
