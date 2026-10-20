"""In-memory stand-ins for unit tests.

The repository fake cannot prove database constraints - integration tests
cover the partial unique index.
"""
from datetime import datetime, timedelta, timezone

from app.models.appointment import ACTIVE_STATUSES, Appointment


class InMemoryAppointmentRepository:
    def __init__(self) -> None:
        self.rows: list[Appointment] = []
        self._next_id = 1
        self.committed = False
        self.rolled_back = False

    def _make(self, doctor_id, patient_id, start_time, status="reserved") -> Appointment:
        a = Appointment(
            doctor_id=doctor_id,
            patient_id=patient_id,
            start_time=start_time,
            status=status,
            cancel_reason=None,
            cancelled_by=None,
        )
        a.id = self._next_id
        self._next_id += 1
        now = datetime.now(timezone.utc)
        a.created_at = now
        a.updated_at = now
        return a

    async def get(self, appointment_id):
        return next((a for a in self.rows if a.id == appointment_id), None)

    async def get_for_update(self, appointment_id):
        return await self.get(appointment_id)

    async def find_active(self, doctor_id, start_time):
        return next(
            (
                a
                for a in self.rows
                if a.doctor_id == doctor_id
                and a.start_time == start_time
                and a.status in ACTIVE_STATUSES
            ),
            None,
        )

    async def list_active_between(self, doctor_id, start, end):
        return [
            a
            for a in self.rows
            if a.doctor_id == doctor_id
            and start <= a.start_time < end
            and a.status in ACTIVE_STATUSES
        ]

    async def list_upcoming_for_patient(self, patient_id, now):
        return sorted(
            [
                a
                for a in self.rows
                if a.patient_id == patient_id
                and a.start_time > now
                and a.status in ACTIVE_STATUSES
            ],
            key=lambda a: a.start_time,
        )

    def add(self, appointment):
        if getattr(appointment, "id", None) is None:
            appointment.id = self._next_id
            self._next_id += 1
        if getattr(appointment, "created_at", None) is None:
            now = datetime.now(timezone.utc)
            appointment.created_at = now
            appointment.updated_at = now
        self.rows.append(appointment)
        return appointment

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    def seed(self, doctor_id, patient_id, start_time, status="reserved"):
        a = self._make(doctor_id, patient_id, start_time, status)
        self.rows.append(a)
        return a


def fixed_clock(when: datetime):
    return lambda: when
