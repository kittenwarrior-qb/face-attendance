from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RegisterResponse(BaseModel):
    success: bool
    employee_id: str
    face_id: int
    message: str = "Face registered successfully"


class GPSPoint(BaseModel):
    latitude: float
    longitude: float


class AttendanceResult(BaseModel):
    action: Literal["check_in", "check_out"]
    odoo_attendance_id: int
    timestamp: datetime
    gps: GPSPoint | None = None


class VerifyResponse(BaseModel):
    success: bool
    employee_id: str | None = None
    score: float | None = Field(default=None, description="Cosine similarity score in [-1, 1]")
    attendance: AttendanceResult | None = None
    message: str | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    detail: str
