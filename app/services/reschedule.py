"""Reschedule in place: one row, one transaction, no gap."""
from app.core.clock import Clock
from app.core.errors import (
    AlreadyCancelled,
    AppointmentExpired,
    AppointmentNotFound,
    InvalidTransition,
    NotAppointmentOwner,
    RejectedNotCancellable,
    SameSlot,
    SlotTaken,
)
from app.core.timezone import to_utc
from app.directories.base import DoctorDirectory
from app.models.appointment import Appointment
from app.repositories.appointments import AppointmentRepository
from app.services.booking import validate_slot


async def reschedule_appointment(
    *,
    appointment_id: int,
    patient_id: int,
    start_time,
    repo: AppointmentRepository,
    doctors: DoctorDirectory,
    clock: Clock,
) -> Appointment:
    appointment = await repo.get_for_update(appointment_id)
    if appointment is None:
        raise AppointmentNotFound()

    if patient_id != appointment.patient_id:
        raise NotAppointmentOwner()

    if appointment.status == "cancelled":
        raise AlreadyCancelled()
    if appointment.status == "rejected":
        raise RejectedNotCancellable("rescheduled")
    if appointment.status not in ("reserved", "confirmed"):
        raise InvalidTransition(appointment.status, "reserved")
    if appointment.start_time <= clock():
        raise AppointmentExpired("rescheduled")

    new_utc = to_utc(start_time)
    if new_utc == appointment.start_time:
        raise SameSlot()

    schedule = await doctors.get_schedule(appointment.doctor_id)
    if schedule is None:
        raise AppointmentNotFound()
    await validate_slot(start_time=new_utc, schedule=schedule, now=clock())

    if await repo.find_active(appointment.doctor_id, new_utc) is not None:
        raise SlotTaken()

    # WHY update the same row: there is never a moment where the old slot is
    # released but the new one is not yet held - the swap is atomic.
    appointment.start_time = new_utc
    appointment.status = "reserved"
    try:
        await repo.flush()
    except Exception as exc:
        await repo.rollback()
        if "uq_active_slot" in str(exc):
            raise SlotTaken() from exc
        raise
    return appointment
