import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from app.services.face_service import FaceService


class LargestFaceSelectionTest(unittest.TestCase):
    def test_trusted_avatar_uses_largest_detected_face(self):
        small = SimpleNamespace(
            bbox=np.array([5, 5, 25, 25]),
            normed_embedding=np.array([0.1, 0.2], dtype=np.float32),
        )
        large = SimpleNamespace(
            bbox=np.array([20, 30, 180, 250]),
            normed_embedding=np.array([0.8, 0.9], dtype=np.float32),
        )
        service = object.__new__(FaceService)
        service._app = Mock()
        service._app.get.return_value = [small, large]

        embedding, bbox = service.extract_largest_face(np.zeros((300, 200, 3), dtype=np.uint8))

        np.testing.assert_array_equal(embedding, large.normed_embedding)
        self.assertEqual(bbox, (20, 30, 160, 220))


if __name__ == "__main__":
    unittest.main()
