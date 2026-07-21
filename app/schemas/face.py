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
    action: Literal["check_in", "check_out"]
    odoo_attendance_id: int
    timestamp: datetime
    gps: GPSPoint | None = None


class VerifyResponse(BaseModel):
    success: bool
    employee_id: str | None = None
    employee_name: str | None = None
    avatar_data_url: str | None = None
    score: float | None = Field(default=None, description="Cosine similarity score in [-1, 1]")
    attendance: AttendanceResult | None = None
    message: str | None = None


class TrackResponse(BaseModel):
    success: bool
    bbox: list[int]


class ErrorResponse(BaseModel):
    success: bool = False
    detail: str
