"""Passive liveness (anti-spoofing) check based on Silent-Face-Anti-Spoofing.

Runs the MiniVision MiniFASNet ensemble (2 models, ~1.7MB each, exported to
ONNX from the official weights at
https://github.com/minivision-ai/Silent-Face-Anti-Spoofing, MIT license) on the
onnxruntime CPU provider that this service already ships for InsightFace.

Classifies a detected face as real (a live person in front of the camera) vs a
presentation attack (printed photo, phone/laptop screen replay). Class layout
of the models' 3-way softmax: index 1 = real, 0 and 2 = two attack types.
"""
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from app.config import Settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# (onnx filename, crop scale around the detected face box). Scales mirror the
# official model names: 2.7_80x80_MiniFASNetV2 / 4_0_0_80x80_MiniFASNetV1SE.
_MODELS = [
    ("2.7_80x80_MiniFASNetV2.onnx", 2.7),
    ("4_0_0_80x80_MiniFASNetV1SE.onnx", 4.0),
]
_INPUT_SIZE = 80

# Default location of the .onnx files (committed with the app).
_DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models_data"

_REAL_CLASS_INDEX = 1


@dataclass
class LivenessResult:
    is_real: bool
    real_score: float  # mean probability of the "real" class across the ensemble


class LivenessService:
    def __init__(self, settings: Settings) -> None:
        model_dir = Path(settings.liveness_model_dir) if settings.liveness_model_dir else _DEFAULT_MODEL_DIR
        self._threshold = settings.liveness_threshold
        self._sessions: list[tuple[ort.InferenceSession, float]] = []
        for filename, scale in _MODELS:
            path = model_dir / filename
            session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            self._sessions.append((session, scale))
        logger.info(
            "Liveness models loaded from %s (threshold=%.2f, mode=%s)",
            model_dir, self._threshold, settings.liveness_mode,
        )

    def check(self, image: np.ndarray, bbox_xywh: tuple[int, int, int, int]) -> LivenessResult:
        """Score the face at `bbox_xywh` (x, y, w, h) in the BGR `image`.

        Each model looks at a differently-scaled crop around the face; their
        softmax outputs are averaged, exactly like the official test.py.
        """
        probs = np.zeros(3, dtype=np.float64)
        for session, scale in self._sessions:
            crop = self._crop(image, bbox_xywh, scale)
            # Model input: BGR, CHW, float32 in the RAW 0-255 range - the
            # official repo's ToTensor deliberately does NOT divide by 255.
            tensor = crop.astype(np.float32).transpose(2, 0, 1)[np.newaxis]
            logits = session.run(None, {"input": tensor})[0][0]
            exp = np.exp(logits - logits.max())
            probs += exp / exp.sum()
        probs /= len(self._sessions)

        real_score = float(probs[_REAL_CLASS_INDEX])
        return LivenessResult(is_real=real_score >= self._threshold, real_score=real_score)

    @staticmethod
    def _crop(image: np.ndarray, bbox_xywh: tuple[int, int, int, int], scale: float) -> np.ndarray:
        """Crop a `scale`-times-enlarged box around the face and resize to the
        model input size. Port of the official CropImage._get_new_box: the
        enlarged box is clamped to stay fully inside the image by shifting
        (not shrinking) it, so the face context ratio stays consistent.
        """
        src_h, src_w = image.shape[:2]
        x, y, box_w, box_h = bbox_xywh

        scale = min((src_h - 1) / box_h, (src_w - 1) / box_w, scale)
        new_w, new_h = box_w * scale, box_h * scale
        center_x, center_y = x + box_w / 2, y + box_h / 2

        left = center_x - new_w / 2
        top = center_y - new_h / 2
        right = center_x + new_w / 2
        bottom = center_y + new_h / 2

        if left < 0:
            right -= left
            left = 0
        if top < 0:
            bottom -= top
            top = 0
        if right > src_w - 1:
            left -= right - src_w + 1
            right = src_w - 1
        if bottom > src_h - 1:
            top -= bottom - src_h + 1
            bottom = src_h - 1

        crop = image[int(top): int(bottom) + 1, int(left): int(right) + 1]
        return cv2.resize(crop, (_INPUT_SIZE, _INPUT_SIZE))
