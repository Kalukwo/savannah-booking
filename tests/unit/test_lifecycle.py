from datetime import datetime

import pytest

from app.core.errors import (
    AppointmentExpired,
    InvalidTransition,
    NotAppointmentDoctor,
)
from app.core.timezone import EAT, to_utc
from app.services import lifecycle

from tests.support.fakes import InMemoryAppointmentRepository


@pytest.fixture
def repo():
    return InMemoryAppointmentRepository()


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=EAT)


async def test_approve_pending(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    result = await lifecycle.approve(
        appointment_id=row.id, doctor_id=1, repo=repo, clock=clock
    )
    assert result.status == "confirmed"


async def test_reject_pending(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    result = await lifecycle.reject(
        appointment_id=row.id, doctor_id=1, repo=repo, clock=clock
    )
    assert result.status == "rejected"


async def test_wrong_doctor_forbidden(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    with pytest.raises(NotAppointmentDoctor):
        await lifecycle.approve(appointment_id=row.id, doctor_id=2, repo=repo, clock=clock)


async def test_cannot_approve_confirmed(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)), status="confirmed")
    with pytest.raises(InvalidTransition):
        await lifecycle.approve(appointment_id=row.id, doctor_id=1, repo=repo, clock=clock)


async def test_expired_pending_cannot_be_approved(repo, clock):
    row = repo.seed(1, 2, to_utc(at(18, 10)))
    with pytest.raises(AppointmentExpired):
        await lifecycle.approve(appointment_id=row.id, doctor_id=1, repo=repo, clock=clock)


async def test_complete_requires_confirmed(repo, clock):
    row = repo.seed(1, 2, to_utc(at(18, 10)))
    with pytest.raises(InvalidTransition):
        await lifecycle.complete(appointment_id=row.id, doctor_id=1, repo=repo, clock=clock)


async def test_complete_only_after_start(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)), status="confirmed")
    with pytest.raises(InvalidTransition):
        await lifecycle.complete(appointment_id=row.id, doctor_id=1, repo=repo, clock=clock)


async def test_complete_confirmed_and_started(repo, clock):
    row = repo.seed(1, 2, to_utc(at(18, 10)), status="confirmed")
    result = await lifecycle.complete(
        appointment_id=row.id, doctor_id=1, repo=repo, clock=clock
    )
    assert result.status == "completed"


async def test_no_show_confirmed_and_started(repo, clock):
    row = repo.seed(1, 2, to_utc(at(18, 10)), status="confirmed")
    result = await lifecycle.no_show(
        appointment_id=row.id, doctor_id=1, repo=repo, clock=clock
    )
    assert result.status == "no_show"
