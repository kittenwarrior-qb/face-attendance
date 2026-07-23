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
        return self.extract_single_face(image)[0]

    def extract_single_face(self, image: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """Like extract_single_embedding, but also returns the face's bounding
        box as (x, y, w, h) ints - needed by the liveness check, which scores
        a scaled crop around the detected face rather than the whole frame.
        """
        faces = self._app.get(image)

        if len(faces) == 0:
            raise NoFaceDetectedError("No face detected in the image")
        if len(faces) > 1:
            raise MultipleFacesDetectedError(
                f"Expected exactly 1 face, found {len(faces)}. Only one person should be in frame."
            )

        return self._face_result(faces[0])

    def extract_largest_face(self, image: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """Return the largest detected face in a trusted master-data image.

        Employee avatars sometimes contain tiny face-like artwork or posters in
        the background.  Interactive attendance scans must still contain exactly
        one face, but Odoo avatar enrollment can safely select the dominant face
        because that image is uploaded by an authenticated administrator.
        """
        faces = self._app.get(image)
        if not faces:
            raise NoFaceDetectedError("No face detected in the image")

        def area(face) -> float:
            x1, y1, x2, y2 = face.bbox
            return max(float(x2 - x1), 0.0) * max(float(y2 - y1), 0.0)

        face = max(faces, key=area)
        if len(faces) > 1:
            logger.info(
                "Trusted avatar contains %d detected faces; enrolling the largest face",
                len(faces),
            )
        return self._face_result(face)

    @staticmethod
    def _face_result(face) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        bbox_xywh = (x1, y1, max(x2 - x1, 1), max(y2 - y1, 1))
        return face.normed_embedding.astype(np.float32), bbox_xywh
