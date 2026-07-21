import base64
import http.client
import json
import xmlrpc.client
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np

from app.config import Settings
from app.utils.exceptions import OdooBusinessValidationError, OdooServiceError
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Fixed name for the ir.attachment holding a JSON-encoded embedding on hr.employee.
# One embedding per employee - re-registering overwrites it.
FACE_EMBEDDING_ATTACHMENT_NAME = "face_embedding.json"

# Odoo XML-RPC fault code for UserError/ValidationError/RedirectWarning (a
# business-rule rejection) - see odoo/addons/base/controllers/rpc.py
# RPC_FAULT_CODE_WARNING. Any other code (typically 1) is a technical/internal
# error, not a business rule, and should not be blindly retried.
_RPC_FAULT_CODE_WARNING = 2

class _TimeoutTransport(xmlrpc.client.Transport):
    """xmlrpc.client.Transport with a socket-level timeout.

    Plain ServerProxy has no timeout and will hang indefinitely if Odoo is
    slow/unreachable, which would stall every /verify request. This bounds
    that wait to `timeout` seconds.
    """

    def __init__(self, timeout: float, use_https: bool = False) -> None:
        super().__init__()
        self._timeout = timeout
        self._use_https = use_https

    def make_connection(self, host: str) -> http.client.HTTPConnection:
        chost, self._extra_headers, x509 = self.get_host_info(host)
        conn_cls = http.client.HTTPSConnection if self._use_https else http.client.HTTPConnection
        return conn_cls(chost, timeout=self._timeout, **(x509 or {}))


@dataclass
class AttendanceRecord:
    action: Literal["check_in", "check_out", "ignored"]
    odoo_attendance_id: int
    timestamp: datetime


class OdooService:
    """Talks to Odoo over XML-RPC. Odoo is the only persistent store this app
    uses: face embeddings live in a JSON ir.attachment on hr.employee, photos
    in hr.employee.image_1920, and attendance in hr.attendance records.

    `employee_id` here is the human-readable code stamped on badges / entered
    at enrollment - it is matched against `hr.employee.barcode`, the standard
    Odoo field used for badge/kiosk-style employee identification. The numeric
    Odoo `hr.employee.id` is resolved from that barcode on demand and cached.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._uid: int | None = None
        self._barcode_cache: dict[str, tuple[int, str]] = {}  # barcode -> (odoo_id, name)
        use_https = settings.odoo_url.startswith("https://")
        transport = _TimeoutTransport(settings.odoo_timeout, use_https=use_https)
        self._common = xmlrpc.client.ServerProxy(
            f"{settings.odoo_url}/xmlrpc/2/common", transport=transport, allow_none=True
        )
        self._models = xmlrpc.client.ServerProxy(
            f"{settings.odoo_url}/xmlrpc/2/object", transport=transport, allow_none=True
        )

    def _authenticate(self) -> int:
        if self._uid is not None:
            return self._uid
        try:
            uid = self._common.authenticate(
                self._settings.odoo_db,
                self._settings.odoo_username,
                self._settings.odoo_password,
                {},
            )
        except Exception as exc:  # xmlrpc.client.Fault / socket errors
            raise OdooServiceError(f"Failed to authenticate with Odoo: {exc}") from exc

        if not uid:
            raise OdooServiceError("Odoo authentication rejected (check ODOO_DB/USERNAME/PASSWORD)")
        self._uid = uid
        return uid

    def _execute(self, model: str, method: str, *args: Any, kwargs: dict[str, Any] | None = None) -> Any:
        uid = self._authenticate()
        try:
            return self._models.execute_kw(
                self._settings.odoo_db,
                uid,
                self._settings.odoo_password,
                model,
                method,
                list(args),
                kwargs or {},
            )
        except xmlrpc.client.Fault as exc:
            message = f"Odoo call {model}.{method} failed: {exc.faultString}"
            if exc.faultCode == _RPC_FAULT_CODE_WARNING:
                raise OdooBusinessValidationError(message) from exc
            raise OdooServiceError(message) from exc
        except Exception as exc:
            raise OdooServiceError(f"Odoo call {model}.{method} failed: {exc}") from exc

    def _resolve_odoo_employee(self, barcode: str) -> tuple[int, str]:
        if barcode in self._barcode_cache:
            return self._barcode_cache[barcode]

        results = self._execute(
            "hr.employee", "search_read", [["barcode", "=", barcode]], kwargs={"fields": ["id", "name"], "limit": 1}
        )
        if not results:
            raise OdooServiceError(
                f"No hr.employee found with barcode='{barcode}' - check the employee's Barcode field in Odoo"
            )
        entry = (results[0]["id"], results[0]["name"])
        self._barcode_cache[barcode] = entry
        return entry

    def _resolve_odoo_employee_id(self, barcode: str) -> int:
        return self._resolve_odoo_employee(barcode)[0]

    def save_face(self, employee_id: str, embedding: np.ndarray, image_bytes: bytes | None = None) -> str:
        """Store the embedding (as a JSON ir.attachment) and optionally the photo
        (in hr.employee.image_1920) for this employee. Odoo is the only place
        this data lives - overwrites any previous registration for the same employee.
        Returns the employee's display name.
        """
        odoo_id, name = self._resolve_odoo_employee(employee_id)
        embedding_json = json.dumps(embedding.tolist()).encode("utf-8")
        self._upsert_attachment(odoo_id, embedding_json)

        if image_bytes is not None:
            self._execute(
                "hr.employee", "write", [odoo_id], {"image_1920": base64.b64encode(image_bytes).decode("ascii")}
            )
        return name

    def get_employee_avatar(self, employee_id: str) -> str | None:
        """Return the registered employee image as base64, if Odoo has one."""
        odoo_id = self._resolve_odoo_employee_id(employee_id)
        result = self._execute(
            "hr.employee", "read", [odoo_id], kwargs={"fields": ["image_1920"]}
        )
        if not result:
            return None
        return result[0].get("image_1920") or None

    def _upsert_attachment(self, res_id: int, data: bytes) -> None:
        existing = self._execute(
            "ir.attachment",
            "search",
            [
                ["res_model", "=", "hr.employee"],
                ["res_id", "=", res_id],
                ["name", "=", FACE_EMBEDDING_ATTACHMENT_NAME],
            ],
            kwargs={"limit": 1},
        )
        vals = {
            "name": FACE_EMBEDDING_ATTACHMENT_NAME,
            "datas": base64.b64encode(data).decode("ascii"),
            "res_model": "hr.employee",
            "res_id": res_id,
            "mimetype": "application/json",
        }
        if existing:
            self._execute("ir.attachment", "write", [existing[0]], vals)
        else:
            self._execute("ir.attachment", "create", vals)

    def load_all_faces(self) -> dict[str, tuple[np.ndarray, str]]:
        """Fetch every registered embedding (+ employee name) from Odoo in two
        batched XML-RPC calls, keyed by barcode. Used to (re)build the
        in-memory match cache.
        """
        employees = self._execute(
            "hr.employee", "search_read", [["barcode", "!=", False]], kwargs={"fields": ["id", "barcode", "name"]}
        )
        id_to_employee = {emp["id"]: (emp["barcode"], emp["name"]) for emp in employees}
        if not id_to_employee:
            return {}

        attachments = self._execute(
            "ir.attachment",
            "search_read",
            [
                ["res_model", "=", "hr.employee"],
                ["res_id", "in", list(id_to_employee.keys())],
                ["name", "=", FACE_EMBEDDING_ATTACHMENT_NAME],
            ],
            kwargs={"fields": ["res_id", "datas"]},
        )

        cache: dict[str, tuple[np.ndarray, str]] = {}
        for attachment in attachments:
            entry = id_to_employee.get(attachment["res_id"])
            if not entry:
                continue
            barcode, name = entry
            try:
                raw = base64.b64decode(attachment["datas"])
                values = json.loads(raw.decode("utf-8"))
                cache[barcode] = (np.array(values, dtype=np.float32), name)
            except Exception as exc:
                logger.error("Failed to parse cached embedding for barcode=%s: %s", barcode, exc)
        return cache

    def create_attendance(
        self,
        employee_id: str,
        timestamp: datetime,
        latitude: float | None = None,
        longitude: float | None = None,
        image_bytes: bytes | None = None,
    ) -> AttendanceRecord:
        """Gửi một raw punch vào Odoo để ghép chung với dữ liệu ZKTeco theo ca."""
        timestamp_utc = (
            timestamp.astimezone(timezone.utc).replace(tzinfo=None)
            if timestamp.tzinfo
            else timestamp
        )
        result = self._execute(
            "satori.attendance.webhook.log",
            "satori_ingest_face_punch",
            employee_id,
            timestamp_utc.strftime("%Y-%m-%d %H:%M:%S"),
            latitude if latitude is not None else False,
            longitude if longitude is not None else False,
            base64.b64encode(image_bytes).decode("ascii") if image_bytes else False,
        )
        attendance_id = result.get("attendance_id")
        if not attendance_id:
            raise OdooServiceError(
                "Odoo kept the raw Face Scan log but could not assign it to a work-shift window"
            )
        action = result.get("action", "ignored")
        logger.info(
            "Odoo %s recorded for employee_id=%s (attendance_id=%s)",
            action,
            employee_id,
            attendance_id,
        )
        return AttendanceRecord(
            action=action,
            odoo_attendance_id=attendance_id,
            timestamp=timestamp,
        )
