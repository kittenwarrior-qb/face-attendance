from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RegisterResponse(BaseModel):
    success: bool
    employee_id: str
    employee_name: str
    message: str = "Face registered successfully"


class GPSPoint(BaseModel):
    latitude: float
    longitude: float


class AttendanceResult(BaseModel):
    action: Literal["check_in", "check_out", "ignored"]
    odoo_attendance_id: int
    timestamp: datetime
    gps: GPSPoint | None = None


class VerifyResponse(BaseModel):
    success: bool
    code: str | None = None
    employee_id: str | None = None
    employee_name: str | None = None
    avatar_data_url: str | None = None
    score: float | None = Field(default=None, description="Cosine similarity score in [-1, 1]")
    attendance: AttendanceResult | None = None
    message: str | None = None


class TrackResponse(BaseModel):
    success: bool
    bbox: list[int]


class RegisteredEmployee(BaseModel):
    employee_id: str
    employee_name: str
    department: str | None = None
    updated_at: datetime | None = None


class AdminEmployeesResponse(BaseModel):
    success: bool = True
    liveness_mode: str
    liveness_threshold: float
    liveness_require_sequence: bool
    liveness_min_frames: int
    total_registered: int
    employees: list[RegisteredEmployee]


class ErrorResponse(BaseModel):
    success: bool = False
    detail: str
