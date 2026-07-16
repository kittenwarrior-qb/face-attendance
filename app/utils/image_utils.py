import os
import uuid
from datetime import datetime

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


def save_face_image(image: np.ndarray, employee_id: int, storage_dir: str) -> str:
    """Persist the original image to disk and return its path."""
    os.makedirs(storage_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{employee_id}_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
    path = os.path.join(storage_dir, filename)
    cv2.imwrite(path, image)
    return path
