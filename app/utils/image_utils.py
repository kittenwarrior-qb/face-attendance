import os
import re
import uuid
from datetime import datetime

import cv2
import numpy as np
from fastapi import UploadFile

from app.utils.exceptions import InvalidImageError

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


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


def save_face_image(image: np.ndarray, employee_id: str, storage_dir: str) -> str:
    """Persist the original image to disk and return its path.

    employee_id is user-supplied (an Odoo barcode) so it's sanitized before
    use in a filename to prevent path traversal / invalid path characters.
    """
    os.makedirs(storage_dir, exist_ok=True)
    safe_employee_id = _UNSAFE_FILENAME_CHARS.sub("_", employee_id)[:64] or "unknown"
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{safe_employee_id}_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
    path = os.path.join(storage_dir, filename)
    cv2.imwrite(path, image)
    return path
