"""Cancellation. The row lock makes concurrent cancels safe."""
from app.core.clock import Clock
from app.core.errors import (
    AlreadyCancelled,
    AppointmentExpired,
    AppointmentNotFound,
    InvalidTransition,
    NotAppointmentDoctor,
    NotAppointmentOwner,
    RejectedNotCancellable,
)
from app.models.appointment import Appointment
from app.repositories.appointments import AppointmentRepository


async def cancel_appointment(
    *,
    appointment_id: int,
    reason: str,
    actor: str,
    actor_id: int,
    repo: AppointmentRepository,
    clock: Clock,
) -> Appointment:
    appointment = await repo.get_for_update(appointment_id)
    if appointment is None:
        raise AppointmentNotFound()

    if actor == "patient":
        if actor_id != appointment.patient_id:
            raise NotAppointmentOwner()
    else:
        if actor_id != appointment.doctor_id:
            raise NotAppointmentDoctor()

    if appointment.status == "cancelled":
        raise AlreadyCancelled()
    if appointment.status == "rejected":
        raise RejectedNotCancellable("cancelled")
    if appointment.status in ("completed", "no_show"):
        raise InvalidTransition(appointment.status, "cancelled")
    if appointment.start_time <= clock():
        raise AppointmentExpired("cancelled")

    appointment.status = "cancelled"
    appointment.cancel_reason = reason.strip()
    appointment.cancelled_by = actor
    await repo.flush()
    return appointment
