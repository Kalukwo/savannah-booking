"""Domain errors and the handlers that render them.

Every failure leaves the API in one shape: {"code", "detail"} (+ "errors" for
validation), so clients can branch on code instead of parsing prose.
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500
    message = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.message
        super().__init__(self.detail)


class ValidationError(AppError):
    code, status_code, message = "VALIDATION_ERROR", 422, "Invalid request"


class DoctorNotFound(AppError):
    code, status_code, message = "DOCTOR_NOT_FOUND", 404, "Doctor not found"


class PatientNotFound(AppError):
    code, status_code, message = "PATIENT_NOT_FOUND", 404, "Patient not found"


class AppointmentNotFound(AppError):
    code, status_code, message = "APPOINTMENT_NOT_FOUND", 404, "Appointment not found"


class OutsideWorkingHours(AppError):
    code, status_code, message = "OUTSIDE_WORKING_HOURS", 422, "Doctor does not work at this time"


class SlotInPast(AppError):
    code, status_code, message = "SLOT_IN_PAST", 422, "Slot is in the past"


class SlotTooSoon(AppError):
    code, status_code, message = "SLOT_TOO_SOON", 422, "Bookings must be at least 1 hour ahead"


class SlotNotAligned(AppError):
    code, status_code, message = "SLOT_NOT_ALIGNED", 422, "Slots start on :00 or :30"


class SameSlot(AppError):
    code, status_code, message = "SAME_SLOT", 422, "New time is the same as the current time"


class SlotTaken(AppError):
    code, status_code, message = "SLOT_TAKEN", 409, "Slot is already booked"


class AlreadyCancelled(AppError):
    code, status_code, message = "ALREADY_CANCELLED", 409, "Appointment is already cancelled"


class RejectedNotCancellable(AppError):
    code, status_code = "REJECTED_NOT_CANCELLABLE", 409

    def __init__(self, action: str = "cancelled") -> None:
        super().__init__(f"Appointment was rejected and cannot be {action}")


class AppointmentExpired(AppError):
    code, status_code = "APPOINTMENT_EXPIRED", 409

    def __init__(self, action: str = "cancelled") -> None:
        super().__init__(f"Appointment has already passed and cannot be {action}")


class InvalidTransition(AppError):
    code, status_code = "INVALID_TRANSITION", 409

    def __init__(self, current: str, target: str, detail: str | None = None) -> None:
        super().__init__(detail or f"Cannot move from {current} to {target}")


class NotAppointmentDoctor(AppError):
    code, status_code = "NOT_APPOINTMENT_DOCTOR", 403

    def __init__(self) -> None:
        super().__init__("You are not allowed to change this appointment")


class NotAppointmentOwner(AppError):
    code, status_code = "NOT_APPOINTMENT_OWNER", 403

    def __init__(self) -> None:
        super().__init__("You are not allowed to change this appointment")


class IdempotencyKeyReused(AppError):
    code, status_code = "IDEMPOTENCY_KEY_REUSED", 409

    def __init__(self) -> None:
        super().__init__("Idempotency key was already used with a different request")


def _payload(code: str, detail: str, errors: list | None = None) -> dict:
    body = {"code": code, "detail": detail}
    if errors:
        body["errors"] = errors
    return body


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content=_payload(exc.code, exc.detail)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        summary = "; ".join(f"{e['field']}: {e['message']}" for e in errors)
        return JSONResponse(
            status_code=422,
            content=_payload("VALIDATION_ERROR", summary or "Invalid request", errors),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return JSONResponse(
            status_code=exc.status_code, content=_payload(code, str(exc.detail))
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Never leak internals; the client only needs to know it was our fault.
        return JSONResponse(
            status_code=500, content=_payload("INTERNAL_ERROR", "Internal server error")
        )
