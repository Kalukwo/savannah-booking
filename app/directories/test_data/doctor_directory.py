"""Stand-in for the doctor service, holding working hours in code.

WHY: this service does not own doctors - in production the rows come from the
doctor service over HTTP, identified by UUID. The assignment forbids doctor
tables and seeding, yet scheduling rules need real hours to test, so the five
doctors live here next to the boundary they will eventually be replaced by.

The UUIDs are FIXED and hand-written (not uuid4) so they stay stable across
runs, can be pasted straight into /docs, and are documented in the README.
"""
import uuid
from datetime import time

from app.directories.base import Schedule

MON_TO_FRI = {0, 1, 2, 3, 4}


def fixed_uuid(n: int) -> uuid.UUID:
    """Readable, deterministic UUID: 00000000-0000-4000-8000-00000000000n."""
    return uuid.UUID(f"00000000-0000-4000-8000-{n:012d}")


DOCTOR_IDS: dict[uuid.UUID, str] = {fixed_uuid(n): f"Doctor {n}" for n in range(1, 6)}

_SCHEDULES: dict[uuid.UUID, Schedule] = {
    fixed_uuid(1): Schedule(time(8, 0), time(17, 0), MON_TO_FRI),
    fixed_uuid(2): Schedule(time(9, 0), time(16, 0), MON_TO_FRI),
    fixed_uuid(3): Schedule(time(10, 0), time(18, 0), MON_TO_FRI),
    fixed_uuid(4): Schedule(time(8, 0), time(14, 0), MON_TO_FRI),
    fixed_uuid(5): Schedule(time(9, 0), time(17, 0), MON_TO_FRI),
}


class DoctorTestDataDirectory:
    async def exists(self, doctor_id: uuid.UUID) -> bool:
        return doctor_id in _SCHEDULES

    async def get_schedule(self, doctor_id: uuid.UUID) -> Schedule | None:
        return _SCHEDULES.get(doctor_id)
