"""Booking rules. The order of checks matters; the first failure wins."""
import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from app.core.clock import Clock
from app.core.errors import (
    DoctorNotFound,
    InvalidTransition,
    OutsideWorkingHours,
    PatientNotFound,
    SlotInPast,
    SlotNotAligned,
    SlotTaken,
    SlotTooSoon,
)
from app.core.timezone import is_aligned, to_eat, to_utc
from app.directories.base import DoctorDirectory, PatientDirectory
from app.models.appointment import Appointment
from app.repositories.appointments import AppointmentRepository

SLOT_MINUTES = 30
MIN_NOTICE = timedelta(hours=1)


async def validate_slot(
    *,
    start_time,
    schedule,
    now,
) -> None:
    """All checks that depend only on the slot itself (old time or new)."""
    local = to_eat(start_time)

    if not is_aligned(start_time):
        raise SlotNotAligned()
    if start_time <= now:
        raise SlotInPast()
    if start_time < now + MIN_NOTICE:
        raise SlotTooSoon()
    if local.weekday() not in schedule.working_days:
        raise OutsideWorkingHours()
    # A slot must fit entirely: starting 16:45 with a 30 minute slot overruns.
    if local.time() < schedule.work_start:
        raise OutsideWorkingHours()
    end_local = local + timedelta(minutes=SLOT_MINUTES)
    if end_local.time() > schedule.work_end:
        raise OutsideWorkingHours()


async def book_appointment(
    *,
    doctor_id: uuid.UUID,
    patient_id: uuid.UUID,
    start_time,
    repo: AppointmentRepository,
    doctors: DoctorDirectory,
    patients: PatientDirectory,
    clock: Clock,
) -> Appointment:
    if not await doctors.exists(doctor_id):
        raise DoctorNotFound()
    if not await patients.exists(patient_id):
        raise PatientNotFound()

    schedule = await doctors.get_schedule(doctor_id)
    if schedule is None:
        raise DoctorNotFound()

    # Everything downstream compares UTC only.
    start_utc = to_utc(start_time)
    now = clock()

    await validate_slot(start_time=start_utc, schedule=schedule, now=now)

    # Cheap pre-check for a friendly error; the unique index below is the
    # real guard, because two requests can pass this line simultaneously.
    if await repo.find_active(doctor_id, start_utc) is not None:
        raise SlotTaken()

    appointment = Appointment(
        doctor_id=doctor_id,
        patient_id=patient_id,
        start_time=start_utc,
        status="reserved",
    )
    repo.add(appointment)
    try:
        await repo.flush()
    except IntegrityError as exc:
        await repo.rollback()
        if "uq_active_slot" in str(exc.orig):
            raise SlotTaken() from exc
        raise
    return appointment
