"""Doctor-driven transitions: approve, reject, complete, no-show."""
from app.core.clock import Clock
from app.core.errors import (
    AppointmentExpired,
    AppointmentNotFound,
    InvalidTransition,
    NotAppointmentDoctor,
)
from app.models.appointment import Appointment
from app.repositories.appointments import AppointmentRepository


async def _load_for_doctor(
    appointment_id: int, doctor_id: int, repo: AppointmentRepository
) -> Appointment:
    appointment = await repo.get_for_update(appointment_id)
    if appointment is None:
        raise AppointmentNotFound()
    # Ownership first: a doctor must not learn anything about a stranger's row.
    if doctor_id != appointment.doctor_id:
        raise NotAppointmentDoctor()
    return appointment


async def approve(
    *, appointment_id: int, doctor_id: int, repo: AppointmentRepository, clock: Clock
) -> Appointment:
    appointment = await _load_for_doctor(appointment_id, doctor_id, repo)
    if appointment.status != "pending":
        raise InvalidTransition(appointment.status, "confirmed")
    if appointment.start_time <= clock():
        raise AppointmentExpired("approved")
    appointment.status = "confirmed"
    await repo.flush()
    return appointment


async def reject(
    *, appointment_id: int, doctor_id: int, repo: AppointmentRepository, clock: Clock
) -> Appointment:
    appointment = await _load_for_doctor(appointment_id, doctor_id, repo)
    if appointment.status != "pending":
        raise InvalidTransition(appointment.status, "rejected")
    if appointment.start_time <= clock():
        raise AppointmentExpired("rejected")
    appointment.status = "rejected"
    await repo.flush()
    return appointment


async def complete(
    *, appointment_id: int, doctor_id: int, repo: AppointmentRepository, clock: Clock
) -> Appointment:
    appointment = await _load_for_doctor(appointment_id, doctor_id, repo)
    if appointment.status != "confirmed":
        raise InvalidTransition(appointment.status, "completed")
    if clock() < appointment.start_time:
        raise InvalidTransition(
            "confirmed", "completed", "Appointment has not started yet"
        )
    appointment.status = "completed"
    await repo.flush()
    return appointment


async def no_show(
    *, appointment_id: int, doctor_id: int, repo: AppointmentRepository, clock: Clock
) -> Appointment:
    appointment = await _load_for_doctor(appointment_id, doctor_id, repo)
    if appointment.status != "confirmed":
        raise InvalidTransition(appointment.status, "no_show")
    if clock() < appointment.start_time:
        raise InvalidTransition(
            "confirmed", "no_show", "Appointment has not started yet"
        )
    appointment.status = "no_show"
    await repo.flush()
    return appointment
