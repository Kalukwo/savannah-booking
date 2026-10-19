from datetime import datetime, timedelta

import pytest

from app.core.errors import (
    DoctorNotFound,
    OutsideWorkingHours,
    PatientNotFound,
    SlotInPast,
    SlotNotAligned,
    SlotTaken,
    SlotTooSoon,
)
from app.core.timezone import EAT, to_utc
from app.directories.test_data.doctor_directory import DoctorTestDataDirectory
from app.directories.test_data.patient_directory import PatientTestDataDirectory
from app.services.booking import book_appointment

from tests.support.fakes import InMemoryAppointmentRepository


@pytest.fixture
def repo():
    return InMemoryAppointmentRepository()


@pytest.fixture
def doctors():
    return DoctorTestDataDirectory()


@pytest.fixture
def patients():
    return PatientTestDataDirectory()


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=EAT)


async def test_valid_booking_is_pending(repo, doctors, patients, clock):
    appointment = await book_appointment(
        doctor_id=1, patient_id=1, start_time=at(20, 10),
        repo=repo, doctors=doctors, patients=patients, clock=clock,
    )
    assert appointment.status == "pending"
    assert appointment.start_time == to_utc(at(20, 10))


async def test_taken_slot_is_rejected(repo, doctors, patients, clock):
    repo.seed(1, 2, to_utc(at(20, 10)))
    with pytest.raises(SlotTaken):
        await book_appointment(
            doctor_id=1, patient_id=1, start_time=at(20, 10),
            repo=repo, doctors=doctors, patients=patients, clock=clock,
        )


async def test_past_slot_rejected(repo, doctors, patients, clock):
    with pytest.raises(SlotInPast):
        await book_appointment(
            doctor_id=1, patient_id=1, start_time=at(18, 10),
            repo=repo, doctors=doctors, patients=patients, clock=clock,
        )


async def test_within_one_hour_rejected(repo, doctors, patients, clock):
    # now is 08:00 EAT; 08:30 is too soon.
    with pytest.raises(SlotTooSoon):
        await book_appointment(
            doctor_id=1, patient_id=1, start_time=at(19, 8, 30),
            repo=repo, doctors=doctors, patients=patients, clock=clock,
        )


async def test_exactly_one_hour_ahead_allowed(repo, doctors, patients, clock):
    appointment = await book_appointment(
        doctor_id=1, patient_id=1, start_time=at(19, 9),
        repo=repo, doctors=doctors, patients=patients, clock=clock,
    )
    assert appointment.status == "pending"


async def test_before_working_hours_rejected(repo, doctors, patients, clock):
    # Doctor 2 starts at 09:00.
    with pytest.raises(OutsideWorkingHours):
        await book_appointment(
            doctor_id=2, patient_id=1, start_time=at(20, 8, 30),
            repo=repo, doctors=doctors, patients=patients, clock=clock,
        )


async def test_slot_overrunning_work_end_rejected(repo, doctors, patients, clock):
    # Doctor 4 works 08:00-14:00; 13:30 + 30 min fits exactly, 14:00 does not.
    with pytest.raises(OutsideWorkingHours):
        await book_appointment(
            doctor_id=4, patient_id=1, start_time=at(20, 14),
            repo=repo, doctors=doctors, patients=patients, clock=clock,
        )


async def test_last_fitting_slot_allowed(repo, doctors, patients, clock):
    appointment = await book_appointment(
        doctor_id=4, patient_id=1, start_time=at(20, 13, 30),
        repo=repo, doctors=doctors, patients=patients, clock=clock,
    )
    assert appointment.status == "pending"


async def test_non_working_day_rejected(repo, doctors, patients, clock):
    # 2026-10-24 is a Saturday.
    with pytest.raises(OutsideWorkingHours):
        await book_appointment(
            doctor_id=1, patient_id=1, start_time=at(24, 10),
            repo=repo, doctors=doctors, patients=patients, clock=clock,
        )


async def test_misaligned_slot_rejected(repo, doctors, patients, clock):
    with pytest.raises(SlotNotAligned):
        await book_appointment(
            doctor_id=1, patient_id=1, start_time=at(20, 10, 15),
            repo=repo, doctors=doctors, patients=patients, clock=clock,
        )


async def test_unknown_doctor_rejected(repo, doctors, patients, clock):
    with pytest.raises(DoctorNotFound):
        await book_appointment(
            doctor_id=99, patient_id=1, start_time=at(20, 10),
            repo=repo, doctors=doctors, patients=patients, clock=clock,
        )


async def test_unknown_patient_rejected(repo, doctors, patients, clock):
    with pytest.raises(PatientNotFound):
        await book_appointment(
            doctor_id=1, patient_id=99, start_time=at(20, 10),
            repo=repo, doctors=doctors, patients=patients, clock=clock,
        )


async def test_slot_bookable_again_after_cancel(repo, doctors, patients, clock):
    first = repo.seed(1, 2, to_utc(at(20, 10)))
    first.status = "cancelled"
    appointment = await book_appointment(
        doctor_id=1, patient_id=1, start_time=at(20, 10),
        repo=repo, doctors=doctors, patients=patients, clock=clock,
    )
    assert appointment.status == "pending"


async def test_slot_bookable_again_after_reject(repo, doctors, patients, clock):
    first = repo.seed(1, 2, to_utc(at(20, 10)))
    first.status = "rejected"
    appointment = await book_appointment(
        doctor_id=1, patient_id=1, start_time=at(20, 10),
        repo=repo, doctors=doctors, patients=patients, clock=clock,
    )
    assert appointment.status == "pending"
