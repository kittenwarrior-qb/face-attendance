import base64

import cv2
import numpy as np
from fastapi import UploadFile

from app.utils.exceptions import InvalidImageError


async def decode_upload_image(file: UploadFile) -> np.ndarray:
    """Read an UploadFile and decode it into a BGR OpenCV image."""
    contents = await file.read()
    if not contents:
        raise InvalidImageError("Uploaded file is empty")

    array = np.frombuffer(contents, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise InvalidImageError("Could not decode uploaded file as an image")
    return image


def encode_image_to_jpeg(image: np.ndarray, quality: int = 90) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise InvalidImageError("Could not encode image as JPEG")
    return buffer.tobytes()


def decode_base64_image(value: str | bytes) -> np.ndarray:
    """Decode an image returned by Odoo's binary field over XML-RPC."""
    try:
        raw = base64.b64decode(value)
    except (TypeError, ValueError) as exc:
        raise InvalidImageError("Odoo avatar is not valid base64 data") from exc
    if not raw:
        raise InvalidImageError("Odoo avatar is empty")

    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise InvalidImageError("Could not decode the Odoo avatar as an image")
    return image
