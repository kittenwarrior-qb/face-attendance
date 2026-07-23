import asyncio
import base64
import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from app.api.register import register_face_from_odoo_avatar, remove_registered_face
from app.utils.exceptions import InvalidImageError


class OdooAvatarRegistrationTest(unittest.TestCase):
    def test_registers_embedding_from_odoo_avatar_without_liveness(self):
        image = np.full((320, 240, 3), 127, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)

        odoo_service = Mock()
        odoo_service.get_employee_avatar.return_value = base64.b64encode(encoded.tobytes()).decode()
        face_service = Mock()
        embedding = np.ones(512, dtype=np.float32)
        face_service.extract_largest_face.return_value = (embedding, (20, 30, 160, 220))
        embedding_service = Mock()
        embedding_service.register.return_value = "Nhân viên Test"

        result = asyncio.run(
            register_face_from_odoo_avatar(
                employee_id="NV001",
                face_service=face_service,
                embedding_service=embedding_service,
                odoo_service=odoo_service,
            )
        )

        self.assertTrue(result.success)
        embedding_service.register.assert_called_once()
        registered_args = embedding_service.register.call_args.args
        self.assertEqual(registered_args[0], "NV001")
        np.testing.assert_array_equal(registered_args[1], embedding)
        self.assertIsNone(registered_args[2])

    def test_missing_odoo_avatar_is_rejected(self):
        odoo_service = Mock()
        odoo_service.get_employee_avatar.return_value = None

        with self.assertRaises(InvalidImageError):
            asyncio.run(
                register_face_from_odoo_avatar(
                    employee_id="NV001",
                    face_service=Mock(),
                    embedding_service=Mock(),
                    odoo_service=odoo_service,
                )
            )

    def test_remove_registration_updates_persistent_store_and_cache(self):
        embedding_service = Mock()

        result = asyncio.run(
            remove_registered_face(
                employee_id="NV001",
                embedding_service=embedding_service,
            )
        )

        self.assertTrue(result["success"])
        embedding_service.unregister.assert_called_once_with("NV001")


if __name__ == "__main__":
    unittest.main()
