import base64
import http.client
import xmlrpc.client
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from app.config import Settings
from app.utils.exceptions import OdooServiceError
from app.utils.logger import get_logger

logger = get_logger(__name__)


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
    action: Literal["check_in", "check_out"]
    odoo_attendance_id: int
    timestamp: datetime


class OdooService:
    """Talks to Odoo over XML-RPC to create/close hr.attendance records.

    Assumes the `employee_id` used by this service is the same id as the
    corresponding `hr.employee` record in Odoo. Adjust `_resolve_odoo_employee_id`
    if your deployment needs a mapping table instead.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._uid: int | None = None
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

    def _execute(self, model: str, method: str, *args: Any) -> Any:
        uid = self._authenticate()
        try:
            return self._models.execute_kw(
                self._settings.odoo_db,
                uid,
                self._settings.odoo_password,
                model,
                method,
                list(args),
            )
        except xmlrpc.client.Fault as exc:
            raise OdooServiceError(f"Odoo call {model}.{method} failed: {exc.faultString}") from exc
        except Exception as exc:
            raise OdooServiceError(f"Odoo call {model}.{method} failed: {exc}") from exc

    def _resolve_odoo_employee_id(self, employee_id: int) -> int:
        return employee_id

    def create_attendance(
        self,
        employee_id: int,
        timestamp: datetime,
        latitude: float | None = None,
        longitude: float | None = None,
        image_bytes: bytes | None = None,
    ) -> AttendanceRecord:
        """Toggle attendance: close the open check-in if one exists, else create a new check-in."""
        odoo_employee_id = self._resolve_odoo_employee_id(employee_id)
        ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        open_ids = self._execute(
            "hr.attendance",
            "search",
            [["employee_id", "=", odoo_employee_id], ["check_out", "=", False]],
        )

        if open_ids:
            attendance_id = open_ids[0]
            vals: dict[str, Any] = {"check_out": ts_str}
            if latitude is not None and longitude is not None:
                vals.update({"out_latitude": latitude, "out_longitude": longitude})
            self._write_with_gps_fallback(attendance_id, vals)
            action: Literal["check_in", "check_out"] = "check_out"
        else:
            vals = {"employee_id": odoo_employee_id, "check_in": ts_str}
            if latitude is not None and longitude is not None:
                vals.update({"in_latitude": latitude, "in_longitude": longitude})
            attendance_id = self._create_with_gps_fallback(vals)
            action = "check_in"

        if self._settings.odoo_attach_image and image_bytes:
            self._attach_image(attendance_id, image_bytes)

        logger.info("Odoo %s recorded for employee_id=%s (attendance_id=%s)", action, employee_id, attendance_id)
        return AttendanceRecord(action=action, odoo_attendance_id=attendance_id, timestamp=timestamp)

    def _write_with_gps_fallback(self, attendance_id: int, vals: dict[str, Any]) -> None:
        try:
            self._execute("hr.attendance", "write", [attendance_id], vals)
        except OdooServiceError as exc:
            if self._is_unknown_field_error(exc) and self._strip_gps_fields(vals):
                logger.warning("GPS fields not available on hr.attendance, retrying without them")
                self._execute("hr.attendance", "write", [attendance_id], vals)
            else:
                raise

    def _create_with_gps_fallback(self, vals: dict[str, Any]) -> int:
        try:
            return self._execute("hr.attendance", "create", vals)
        except OdooServiceError as exc:
            if self._is_unknown_field_error(exc) and self._strip_gps_fields(vals):
                logger.warning("GPS fields not available on hr.attendance, retrying without them")
                return self._execute("hr.attendance", "create", vals)
            raise

    @staticmethod
    def _is_unknown_field_error(exc: OdooServiceError) -> bool:
        message = str(exc).lower()
        return "invalid field" in message or "unknown field" in message or "latitude" in message

    @staticmethod
    def _strip_gps_fields(vals: dict[str, Any]) -> bool:
        gps_keys = ["in_latitude", "in_longitude", "out_latitude", "out_longitude"]
        removed = False
        for key in gps_keys:
            if vals.pop(key, None) is not None:
                removed = True
        return removed

    def _attach_image(self, attendance_id: int, image_bytes: bytes) -> None:
        try:
            self._execute(
                "ir.attachment",
                "create",
                {
                    "name": f"attendance_{attendance_id}.jpg",
                    "type": "binary",
                    "datas": base64.b64encode(image_bytes).decode("ascii"),
                    "res_model": "hr.attendance",
                    "res_id": attendance_id,
                },
            )
        except OdooServiceError as exc:
            logger.error("Failed to attach image to hr.attendance %s: %s", attendance_id, exc)
