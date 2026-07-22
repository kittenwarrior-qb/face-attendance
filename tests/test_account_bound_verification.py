import unittest
from unittest.mock import AsyncMock, Mock, patch

import numpy as np

from app.api.verify import verify_face
from app.config import Settings
from app.services.embedding_service import MatchResult
from app.services.odoo_service import AttendanceRecord
from app.utils.exceptions import OdooBusinessValidationError


class AccountBoundVerificationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.face_service = Mock()
        self.face_service.extract_single_face.return_value = (
            np.array([1.0], dtype=np.float32),
            [0, 0, 10, 10],
        )
        self.embedding_service = Mock()
        self.embedding_service.find_employee_match.return_value = MatchResult(
            employee_id="FACE001",
            employee_name="Face Employee",
            score=0.91,
        )
        self.odoo_service = Mock()
        self.odoo_service.get_employee_avatar.return_value = None
        self.odoo_service.create_attendance.return_value = AttendanceRecord(
            action="check_in",
            odoo_attendance_id=10,
            timestamp=Mock(),
        )
        self.settings = Settings(liveness_mode="off", odoo_attach_image=False)

    async def _verify(self, token="signed-account-token", expected_employee_id="FACE001"):
        with patch(
            "app.api.verify.decode_upload_image",
            new=AsyncMock(return_value=np.zeros((20, 20, 3), dtype=np.uint8)),
        ):
            return await verify_face(
                file=Mock(),
                files=None,
                latitude=None,
                longitude=None,
                account_token=token,
                expected_employee_id=expected_employee_id,
                face_service=self.face_service,
                embedding_service=self.embedding_service,
                odoo_service=self.odoo_service,
                liveness_service=None,
                settings=self.settings,
            )

    async def test_signed_account_token_is_forwarded_to_odoo(self):
        response = await self._verify()

        self.assertTrue(response.success)
        self.assertEqual(
            self.odoo_service.create_attendance.call_args.kwargs["account_token"],
            "signed-account-token",
        )

    async def test_odoo_account_face_mismatch_has_specific_error_code(self):
        self.odoo_service.create_attendance.side_effect = OdooBusinessValidationError(
            "Khuôn mặt không khớp với tài khoản Odoo đang đăng nhập."
        )

        response = await self._verify()

        self.assertFalse(response.success)
        self.assertEqual(response.code, "AccountFaceMismatchError")


if __name__ == "__main__":
    unittest.main()
