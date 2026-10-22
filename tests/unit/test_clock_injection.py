"""The clock is the only source of "now", so freezing it must change behaviour."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.errors import SlotTooSoon
from app.core.timezone import EAT
from app.directories.test_data.doctor_directory import DoctorTestDataDirectory
from app.directories.test_data.patient_directory import PatientTestDataDirectory
from app.services.booking import book_appointment

from tests.support.fakes import InMemoryAppointmentRepository

from app.directories.test_data.doctor_directory import fixed_uuid

def _doc(n: int):
    return fixed_uuid(n)


def _pat(n: int):
    return fixed_uuid(100 + n)

async def test_same_request_allowed_or_rejected_by_clock():
    doctors, patients = DoctorTestDataDirectory(), PatientTestDataDirectory()
    start = datetime(2026, 10, 20, 10, 0, tzinfo=EAT)

    early = lambda: start - timedelta(hours=2)
    await book_appointment(
        doctor_id=_doc(1), patient_id=_pat(1), start_time=start,
        repo=InMemoryAppointmentRepository(), doctors=doctors, patients=patients, clock=early,
    )

    too_late = lambda: start - timedelta(minutes=30)
    with pytest.raises(SlotTooSoon):
        await book_appointment(
            doctor_id=_doc(1), patient_id=_pat(1), start_time=start,
            repo=InMemoryAppointmentRepository(), doctors=doctors, patients=patients,
            clock=too_late,
        )
