"""Slot generation for a single doctor on a single EAT day."""
import uuid
from datetime import date, datetime, timedelta, timezone

from app.core.clock import Clock
from app.core.errors import DoctorNotFound
from app.core.timezone import EAT, eat_day_to_utc_range, to_eat
from app.directories.base import DoctorDirectory
from app.repositories.appointments import AppointmentRepository
from app.services.booking import MIN_NOTICE, SLOT_MINUTES


async def generate_slots(
    *,
    doctor_id: uuid.UUID,
    day: date,
    repo: AppointmentRepository,
    doctors: DoctorDirectory,
    clock: Clock,
) -> list[datetime]:
    schedule = await doctors.get_schedule(doctor_id)
    if schedule is None:
        raise DoctorNotFound()

    if day.weekday() not in schedule.working_days:
        return []

    day_start, day_end = eat_day_to_utc_range(day)
    taken = {
        a.start_time
        for a in await repo.list_active_between(doctor_id, day_start, day_end)
    }
    earliest = clock() + MIN_NOTICE

    # Slots are generated on the EAT wall clock, then compared in UTC.
    slots: list[datetime] = []
    cursor = datetime.combine(day, schedule.work_start, tzinfo=EAT)
    finish = datetime.combine(day, schedule.work_end, tzinfo=EAT)
    while cursor + timedelta(minutes=SLOT_MINUTES) <= finish:
        slot_utc = cursor.astimezone(timezone.utc)
        if slot_utc not in taken and slot_utc >= earliest:
            slots.append(to_eat(slot_utc))
        cursor += timedelta(minutes=SLOT_MINUTES)
    return slots
