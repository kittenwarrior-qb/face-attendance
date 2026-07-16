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
