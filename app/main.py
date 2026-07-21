from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import health, register, track, ui, verify
from app.config import get_settings
from app.services.embedding_service import EmbeddingService
from app.services.face_service import FaceService
from app.services.odoo_service import OdooService
from app.utils.exceptions import (
    FaceAttendanceError,
    InvalidImageError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    OdooServiceError,
    SpoofDetectedError,
)
from app.utils.logger import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)

ERROR_STATUS_MAP: dict[type[FaceAttendanceError], int] = {
    InvalidImageError: 400,
    NoFaceDetectedError: 422,
    MultipleFacesDetectedError: 422,
    SpoofDetectedError: 422,
    OdooServiceError: 502,
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Initializing services...")
    app.state.face_service = FaceService(settings)
    app.state.odoo_service = OdooService(settings)
    app.state.embedding_service = EmbeddingService(app.state.odoo_service, settings.face_match_threshold)

    if settings.liveness_active:
        from app.services.liveness_service import LivenessService

        app.state.liveness_service = LivenessService(settings)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list or ["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(register.router)
app.include_router(verify.router)
app.include_router(track.router)
app.include_router(ui.router)
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")


@app.exception_handler(FaceAttendanceError)
async def face_attendance_error_handler(request: Request, exc: FaceAttendanceError) -> JSONResponse:
    status_code = ERROR_STATUS_MAP.get(type(exc), 400)
    # `code` is the stable, language-independent exception class name; `detail`
    # is an English message for logs/developers. Clients should localize UI
    # text off `code`, not parse `detail` (kept in English regardless of the
    # server's own locale, unlike Odoo's own error strings).
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "code": type(exc).__name__, "detail": str(exc)},
    )
