from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    # Reject unknown fields so a typo is an error, not a silently ignored value.
    model_config = ConfigDict(extra="forbid")


class AppointmentCreate(StrictModel):
    doctor_id: int = Field(..., examples=[1])
    patient_id: int = Field(..., examples=[2])
    start_time: datetime = Field(
        ...,
        description="Slot start. Naive values are treated as EAT.",
        examples=["2026-10-20T10:00:00+03:00"],
    )


class CancelRequest(StrictModel):
    reason: str = Field(..., max_length=500, examples=["Patient is unwell"])
    actor: Literal["patient", "doctor"] = Field(..., examples=["patient"])
    actor_id: int = Field(..., examples=[2])


class RescheduleRequest(StrictModel):
    patient_id: int = Field(..., examples=[2])
    start_time: datetime = Field(..., examples=["2026-10-21T14:30:00+03:00"])


class DoctorActionRequest(StrictModel):
    doctor_id: int = Field(..., examples=[1])


class AppointmentResponse(BaseModel):
    id: int
    doctor_id: int
    patient_id: int
    start_time: datetime
    status: str
    cancel_reason: str | None = None
    cancelled_by: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, appointment) -> "AppointmentResponse":
        from app.core.timezone import to_eat

        return cls(
            id=appointment.id,
            doctor_id=appointment.doctor_id,
            patient_id=appointment.patient_id,
            start_time=to_eat(appointment.start_time),
            status=appointment.status,
            cancel_reason=appointment.cancel_reason,
            cancelled_by=appointment.cancelled_by,
            created_at=to_eat(appointment.created_at),
            updated_at=to_eat(appointment.updated_at),
        )


class AvailabilityResponse(BaseModel):
    doctor_id: int
    date: str
    slots: list[datetime]
