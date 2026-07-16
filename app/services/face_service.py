import numpy as np
from insightface.app import FaceAnalysis

from app.config import Settings
from app.utils.exceptions import MultipleFacesDetectedError, NoFaceDetectedError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FaceService:
    """Wraps InsightFace (buffalo_l) for detection, alignment and embedding.

    Detection, landmark-based alignment and ArcFace embedding all happen
    inside `FaceAnalysis.get()` - no separate alignment step is needed.
    """

    def __init__(self, settings: Settings) -> None:
        logger.info("Loading InsightFace model pack '%s' ...", settings.insightface_model_pack)
        # Attendance only needs detection (to align) + recognition (to embed).
        # Skipping genderage/landmark_3d_68/landmark_2d_106 cuts inference time by ~30%.
        self._app = FaceAnalysis(
            name=settings.insightface_model_pack,
            providers=["CPUExecutionProvider"],
            allowed_modules=["detection", "recognition"],
        )
        self._app.prepare(ctx_id=settings.insightface_ctx_id, det_size=settings.insightface_det_size_tuple)
        logger.info("InsightFace model ready.")

    def extract_single_embedding(self, image: np.ndarray) -> np.ndarray:
        """Detect exactly one face in `image` and return its 512-d normalized embedding.

        Raises NoFaceDetectedError / MultipleFacesDetectedError otherwise, since
        this system expects exactly one person in front of the camera at a time.
        """
        faces = self._app.get(image)

        if len(faces) == 0:
            raise NoFaceDetectedError("No face detected in the image")
        if len(faces) > 1:
            raise MultipleFacesDetectedError(
                f"Expected exactly 1 face, found {len(faces)}. Only one person should be in frame."
            )

        return faces[0].normed_embedding.astype(np.float32)
