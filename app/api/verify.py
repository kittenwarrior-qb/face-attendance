from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_embedding_service, get_face_service, get_liveness_service, get_odoo_service
from app.config import Settings, get_settings
from app.schemas.face import AttendanceResult, GPSPoint, VerifyResponse
from app.services.embedding_service import EmbeddingService
from app.services.face_service import FaceService
from app.services.odoo_service import OdooService
from app.utils.exceptions import OdooBusinessValidationError, OdooServiceError, SpoofDetectedError
from app.utils.image_utils import decode_upload_image, encode_image_to_jpeg
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["face"])


@router.post("/verify", response_model=VerifyResponse)
async def verify_face(
    file: UploadFile = File(..., description="First camera frame containing exactly one face"),
    files: list[UploadFile] | None = File(None, description="Additional camera frames"),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    account_token: str = Form(..., description="Short-lived token issued by the logged-in Odoo account"),
    expected_employee_id: str = Form(..., description="Employee barcode bound to the logged-in Odoo account"),
    face_service: FaceService = Depends(get_face_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    odoo_service: OdooService = Depends(get_odoo_service),
    liveness_service=Depends(get_liveness_service),
    settings: Settings = Depends(get_settings),
) -> VerifyResponse:
    image = await decode_upload_image(file)
    embedding, bbox = face_service.extract_single_face(image)

    if liveness_service is not None:
        frames = [(image, bbox)]
        if files:
            for extra_file in files:
                extra_image = await decode_upload_image(extra_file)
                _, extra_bbox = face_service.extract_single_face(extra_image)
                frames.append((extra_image, extra_bbox))
        if settings.liveness_require_sequence and len(frames) < settings.liveness_min_frames:
            raise SpoofDetectedError(
                f"Verification requires at least {settings.liveness_min_frames} camera frames"
            )
        liveness = liveness_service.check_sequence(frames) if len(frames) > 1 else liveness_service.check(image, bbox)
        if not liveness.is_real:
            if settings.liveness_mode == "enforce":
                logger.warning("Spoof attempt blocked (real_score=%.3f)", liveness.real_score)
                raise SpoofDetectedError(
                    f"Face looks like a photo/screen, not a live person "
                    f"(real_score={liveness.real_score:.3f}, temporal_delta={liveness.temporal_delta:.4f})"
                )
            # warn mode: log for threshold calibration, but let the scan through.
            logger.warning("Liveness below threshold but mode=warn (real_score=%.3f)", liveness.real_score)
        else:
            logger.info("Liveness ok (real_score=%.3f)", liveness.real_score)

    match = embedding_service.find_employee_match(embedding, expected_employee_id)
    if match is None:
        registered = embedding_service.registered_employee(expected_employee_id)
        if registered is None:
            logger.warning("Verification blocked: no embedding for account employee=%s", expected_employee_id)
            return VerifyResponse(
                success=False,
                code="FaceNotRegisteredError",
                employee_id=expected_employee_id,
                message="Tài khoản chưa có dữ liệu khuôn mặt. Vui lòng liên hệ HCNS đăng ký lại.",
            )
        logger.info(
            "Verification failed for account employee=%s (threshold %.3f)",
            expected_employee_id,
            settings.face_match_threshold,
        )
        return VerifyResponse(
            success=False,
            code="AccountFaceMismatchError",
            employee_id=registered.employee_id,
            employee_name=registered.employee_name,
            score=registered.score,
            message="Khuôn mặt không khớp với tài khoản đang đăng nhập. Không thể chấm công cho người khác.",
        )

    avatar_data_url = None
    try:
        avatar = odoo_service.get_employee_avatar(match.employee_id)
        if avatar:
            avatar_data_url = f"data:image/jpeg;base64,{avatar}"
    except OdooServiceError as exc:
        # Avatar is a confirmation aid; it must not make an otherwise valid
        # attendance scan fail when the image field is unavailable.
        logger.warning("Could not load avatar for employee_id=%s: %s", match.employee_id, exc)

    gps = GPSPoint(latitude=latitude, longitude=longitude) if latitude is not None and longitude is not None else None

    image_bytes = encode_image_to_jpeg(image) if settings.odoo_attach_image else None

    try:
        attendance = odoo_service.create_attendance(
            employee_id=match.employee_id,
            timestamp=datetime.now(timezone.utc),
            latitude=latitude,
            longitude=longitude,
            image_bytes=image_bytes,
            account_token=account_token,
        )
    except OdooBusinessValidationError as exc:
        logger.info("Attendance rejected by Odoo for employee_id=%s: %s", match.employee_id, exc)
        error_text = str(exc)
        face_scan_not_allowed = "chưa được cấp quyền chấm công bằng Face Scan" in error_text
        account_face_mismatch = "Khuôn mặt không khớp với tài khoản" in error_text
        account_token_error = "Phiên Face Scan" in error_text
        error_code = (
            "AccountFaceMismatchError"
            if account_face_mismatch
            else "AccountTokenError"
            if account_token_error
            else "FaceScanNotAllowedError"
            if face_scan_not_allowed
            else "AttendanceRejectedError"
        )
        return VerifyResponse(
            success=False,
            code=error_code,
            employee_id=match.employee_id,
            employee_name=match.employee_name,
            avatar_data_url=avatar_data_url,
            score=match.score,
            message=(
                "Khuôn mặt không khớp với tài khoản đang đăng nhập. Không thể chấm công cho người khác."
                if account_face_mismatch
                else "Phiên chấm công không hợp lệ hoặc đã hết hạn. Vui lòng đóng và mở lại."
                if account_token_error
                else "Nhân viên này chưa được cấp quyền chấm công bằng Face Scan. Vui lòng liên hệ HCNS."
                if face_scan_not_allowed
                else "Đã nhận diện khuôn mặt nhưng Odoo từ chối chấm công. Vui lòng liên hệ HCNS."
            ),
        )
    except OdooServiceError as exc:
        logger.error("Verified employee_id=%s but Odoo attendance failed: %s", match.employee_id, exc)
        return VerifyResponse(
            success=False,
            code="AttendanceServiceError",
            employee_id=match.employee_id,
            employee_name=match.employee_name,
            avatar_data_url=avatar_data_url,
            score=match.score,
            message="Đã nhận diện khuôn mặt nhưng không thể ghi nhận chấm công. Vui lòng liên hệ HCNS.",
        )

    return VerifyResponse(
        success=True,
        employee_id=match.employee_id,
        employee_name=match.employee_name,
        avatar_data_url=avatar_data_url,
        score=match.score,
        attendance=AttendanceResult(
            action=attendance.action,
            odoo_attendance_id=attendance.odoo_attendance_id,
            timestamp=attendance.timestamp,
            gps=gps,
        ),
        message="Attendance recorded",
    )
