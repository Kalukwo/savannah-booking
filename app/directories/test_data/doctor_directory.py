"""Stand-in for the doctor service, holding working hours in code.

WHY: the assignment forbids doctor tables and seeding, yet scheduling rules
need real hours to test. This keeps the data next to the boundary it will
eventually be replaced by.
"""
from datetime import time

from app.directories.base import Schedule

MON_TO_FRI = {0, 1, 2, 3, 4}

_SCHEDULES: dict[int, Schedule] = {
    1: Schedule(time(8, 0), time(17, 0), MON_TO_FRI),
    2: Schedule(time(9, 0), time(16, 0), MON_TO_FRI),
    3: Schedule(time(10, 0), time(18, 0), MON_TO_FRI),
    4: Schedule(time(8, 0), time(14, 0), MON_TO_FRI),
    5: Schedule(time(9, 0), time(17, 0), MON_TO_FRI),
}


class DoctorTestDataDirectory:
    async def exists(self, doctor_id: int) -> bool:
        return doctor_id in _SCHEDULES

    async def get_schedule(self, doctor_id: int) -> Schedule | None:
        return _SCHEDULES.get(doctor_id)
