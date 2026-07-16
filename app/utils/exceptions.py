"""Custom exception types, mapped to HTTP responses in app.main."""


class FaceAttendanceError(Exception):
    """Base class for all domain errors in this service."""


class InvalidImageError(FaceAttendanceError):
    """Raised when the uploaded file cannot be decoded as an image."""


class NoFaceDetectedError(FaceAttendanceError):
    """Raised when no face is found in the image."""


class MultipleFacesDetectedError(FaceAttendanceError):
    """Raised when more than one face is found in the image."""


class OdooServiceError(FaceAttendanceError):
    """Raised when the Odoo XML-RPC call fails."""


class OdooBusinessValidationError(OdooServiceError):
    """Raised when Odoo rejects a write due to its own business rules
    (e.g. hr.attendance's overlap check - "employee hasn't checked out yet"),
    as opposed to a technical/connectivity failure. Detected via Odoo's XML-RPC
    faultCode (2 = UserError/ValidationError), not by parsing the message text,
    since that text is localized to whatever language the Odoo UI uses.
    """
