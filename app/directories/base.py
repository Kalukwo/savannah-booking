"""Boundaries to the services that own doctors and patients.

WHY: in the real system these are HTTP clients - working hours belong to
the doctor service and patient records live elsewhere. Defining Protocols
means the booking rules never learn where the data came from, and tests can
hand in plain in-memory implementations.
"""
import uuid
from dataclasses import dataclass
from datetime import time
from typing import Protocol


@dataclass(frozen=True)
class Schedule:
    work_start: time
    work_end: time
    working_days: set[int]  # ISO weekday numbers, Monday=0 .. Sunday=6


class DoctorDirectory(Protocol):
    async def exists(self, doctor_id: uuid.UUID) -> bool: ...

    async def get_schedule(self, doctor_id: uuid.UUID) -> Schedule | None: ...


class PatientDirectory(Protocol):
    async def exists(self, patient_id: uuid.UUID) -> bool: ...
