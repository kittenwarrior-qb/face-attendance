import base64
import json
import unittest
from unittest.mock import Mock

import numpy as np

from app.services.odoo_service import OdooService


class EmbeddingCacheCompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(OdooService)
        self.service._execute = Mock()

    def test_active_legacy_embedding_is_loaded_without_new_status_fields(self):
        embedding = [0.1, 0.2, 0.3]
        self.service._execute.side_effect = [
            [{"id": 391, "barcode": "SH0105", "name": "Bui Dinh Quoc", "active": True}],
            [{"res_id": 391, "datas": base64.b64encode(json.dumps(embedding).encode()).decode()}],
        ]

        cache = self.service.load_all_faces()

        self.assertEqual(list(cache), ["SH0105"])
        self.assertEqual(cache["SH0105"][1], "Bui Dinh Quoc")
        np.testing.assert_allclose(cache["SH0105"][0], embedding)
        employee_domain = self.service._execute.call_args_list[0].args[2]
        self.assertIn(["active", "=", True], employee_domain)
        self.assertNotIn(["satori_face_enrollment_state", "=", "registered"], employee_domain)

    def test_no_active_employee_means_no_attachment_lookup(self):
        self.service._execute.return_value = []

        self.assertEqual(self.service.load_all_faces(), {})
        self.service._execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
