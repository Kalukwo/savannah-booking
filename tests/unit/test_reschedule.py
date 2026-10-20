from datetime import datetime

import pytest

from app.core.errors import (
    AlreadyCancelled,
    AppointmentExpired,
    NotAppointmentOwner,
    RejectedNotCancellable,
    SameSlot,
    SlotTaken,
)
from app.core.timezone import EAT, to_utc
from app.directories.test_data.doctor_directory import DoctorTestDataDirectory
from app.services.reschedule import reschedule_appointment

from tests.support.fakes import InMemoryAppointmentRepository


@pytest.fixture
def repo():
    return InMemoryAppointmentRepository()


@pytest.fixture
def doctors():
    return DoctorTestDataDirectory()


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=EAT)


async def test_same_row_updated(repo, doctors, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    original_id = row.id
    result = await reschedule_appointment(
        appointment_id=row.id, patient_id=2, start_time=at(20, 11),
        repo=repo, doctors=doctors, clock=clock,
    )
    assert result.id == original_id
    assert result.start_time == to_utc(at(20, 11))
    assert result.status == "reserved"
    assert len(repo.rows) == 1


async def test_new_slot_taken_keeps_original(repo, doctors, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    repo.seed(1, 3, to_utc(at(20, 11)))
    with pytest.raises(SlotTaken):
        await reschedule_appointment(
            appointment_id=row.id, patient_id=2, start_time=at(20, 11),
            repo=repo, doctors=doctors, clock=clock,
        )
    assert row.start_time == to_utc(at(20, 10))


async def test_same_slot_rejected(repo, doctors, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    with pytest.raises(SameSlot):
        await reschedule_appointment(
            appointment_id=row.id, patient_id=2, start_time=at(20, 10),
            repo=repo, doctors=doctors, clock=clock,
        )


async def test_wrong_patient_forbidden(repo, doctors, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    with pytest.raises(NotAppointmentOwner):
        await reschedule_appointment(
            appointment_id=row.id, patient_id=3, start_time=at(20, 11),
            repo=repo, doctors=doctors, clock=clock,
        )


async def test_cancelled_cannot_be_rescheduled(repo, doctors, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)), status="cancelled")
    with pytest.raises(AlreadyCancelled):
        await reschedule_appointment(
            appointment_id=row.id, patient_id=2, start_time=at(20, 11),
            repo=repo, doctors=doctors, clock=clock,
        )


async def test_rejected_cannot_be_rescheduled(repo, doctors, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)), status="rejected")
    with pytest.raises(RejectedNotCancellable):
        await reschedule_appointment(
            appointment_id=row.id, patient_id=2, start_time=at(20, 11),
            repo=repo, doctors=doctors, clock=clock,
        )


async def test_expired_cannot_be_rescheduled(repo, doctors, clock):
    row = repo.seed(1, 2, to_utc(at(18, 10)))
    with pytest.raises(AppointmentExpired):
        await reschedule_appointment(
            appointment_id=row.id, patient_id=2, start_time=at(20, 11),
            repo=repo, doctors=doctors, clock=clock,
        )
