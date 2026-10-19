"""Dependency wiring: the only place that knows concrete implementations."""
from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, utc_now
from app.db.session import get_session
from app.directories.test_data.doctor_directory import DoctorTestDataDirectory
from app.directories.test_data.patient_directory import PatientTestDataDirectory
from app.repositories.appointments import AppointmentRepository
from app.repositories.idempotency import IdempotencyRepository

_doctor_directory = DoctorTestDataDirectory()
_patient_directory = PatientTestDataDirectory()


def get_doctor_directory() -> DoctorTestDataDirectory:
    # Swap this for an HTTP client when the real doctor service exists.
    return _doctor_directory


def get_patient_directory() -> PatientTestDataDirectory:
    return _patient_directory


def get_clock() -> Clock:
    return utc_now


async def get_appointment_repo(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[AppointmentRepository]:
    yield AppointmentRepository(session)


def get_idempotency_store(
    session: AsyncSession = Depends(get_session),
) -> IdempotencyRepository:
    return IdempotencyRepository(session)
