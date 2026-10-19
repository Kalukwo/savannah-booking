from datetime import date, datetime

import pytest

from app.core.errors import DoctorNotFound
from app.core.timezone import EAT, to_utc
from app.directories.test_data.doctor_directory import DoctorTestDataDirectory
from app.services.availability import generate_slots

from tests.support.fakes import InMemoryAppointmentRepository


@pytest.fixture
def repo():
    return InMemoryAppointmentRepository()


@pytest.fixture
def doctors():
    return DoctorTestDataDirectory()


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=EAT)


async def test_slots_follow_schedule(repo, doctors, clock):
    # Doctor 4 works 08:00-14:00: twelve 30 minute slots.
    slots = await generate_slots(
        doctor_id=4, day=date(2026, 10, 21), repo=repo, doctors=doctors, clock=clock
    )
    assert len(slots) == 12
    assert slots[0].hour == 8 and slots[0].minute == 0
    assert slots[-1].hour == 13 and slots[-1].minute == 30


async def test_taken_slot_excluded(repo, doctors, clock):
    repo.seed(1, 2, to_utc(at(20, 10)))
    slots = await generate_slots(
        doctor_id=1, day=date(2026, 10, 20), repo=repo, doctors=doctors, clock=clock
    )
    assert at(20, 10) not in slots
    assert at(20, 10, 30) in slots


async def test_cancelled_slot_reappears(repo, doctors, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    row.status = "cancelled"
    slots = await generate_slots(
        doctor_id=1, day=date(2026, 10, 20), repo=repo, doctors=doctors, clock=clock
    )
    assert at(20, 10) in slots


async def test_past_and_too_soon_excluded(repo, doctors, clock):
    # now is 2026-10-19 08:00 EAT, so only 09:00 onward survives today.
    slots = await generate_slots(
        doctor_id=1, day=date(2026, 10, 19), repo=repo, doctors=doctors, clock=clock
    )
    assert all(slot >= at(19, 9) for slot in slots)
    assert at(19, 9) in slots


async def test_weekend_is_empty(repo, doctors, clock):
    slots = await generate_slots(
        doctor_id=1, day=date(2026, 10, 24), repo=repo, doctors=doctors, clock=clock
    )
    assert slots == []


async def test_unknown_doctor(repo, doctors, clock):
    with pytest.raises(DoctorNotFound):
        await generate_slots(
            doctor_id=99, day=date(2026, 10, 20), repo=repo, doctors=doctors, clock=clock
        )
