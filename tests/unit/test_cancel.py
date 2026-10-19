from datetime import datetime

import pytest

from app.core.errors import (
    AlreadyCancelled,
    AppointmentExpired,
    AppointmentNotFound,
    InvalidTransition,
    NotAppointmentDoctor,
    NotAppointmentOwner,
    RejectedNotCancellable,
)
from app.core.timezone import EAT, to_utc
from app.services.cancel import cancel_appointment

from tests.support.fakes import InMemoryAppointmentRepository


@pytest.fixture
def repo():
    return InMemoryAppointmentRepository()


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=EAT)


async def test_patient_cancels(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    result = await cancel_appointment(
        appointment_id=row.id, reason="Unwell", actor="patient", actor_id=2,
        repo=repo, clock=clock,
    )
    assert result.status == "cancelled"
    assert result.cancelled_by == "patient"
    assert result.cancel_reason == "Unwell"


async def test_doctor_cancels(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    result = await cancel_appointment(
        appointment_id=row.id, reason="Emergency", actor="doctor", actor_id=1,
        repo=repo, clock=clock,
    )
    assert result.cancelled_by == "doctor"


async def test_wrong_patient_forbidden(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    with pytest.raises(NotAppointmentOwner):
        await cancel_appointment(
            appointment_id=row.id, reason="Unwell", actor="patient", actor_id=3,
            repo=repo, clock=clock,
        )


async def test_wrong_doctor_forbidden(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)))
    with pytest.raises(NotAppointmentDoctor):
        await cancel_appointment(
            appointment_id=row.id, reason="Emergency", actor="doctor", actor_id=2,
            repo=repo, clock=clock,
        )


async def test_unknown_appointment(repo, clock):
    with pytest.raises(AppointmentNotFound):
        await cancel_appointment(
            appointment_id=99, reason="Unwell", actor="patient", actor_id=2,
            repo=repo, clock=clock,
        )


async def test_already_cancelled(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)), status="cancelled")
    with pytest.raises(AlreadyCancelled):
        await cancel_appointment(
            appointment_id=row.id, reason="Unwell", actor="patient", actor_id=2,
            repo=repo, clock=clock,
        )


async def test_rejected_cannot_be_cancelled(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)), status="rejected")
    with pytest.raises(RejectedNotCancellable):
        await cancel_appointment(
            appointment_id=row.id, reason="Unwell", actor="patient", actor_id=2,
            repo=repo, clock=clock,
        )


async def test_expired_cannot_be_cancelled(repo, clock):
    row = repo.seed(1, 2, to_utc(at(18, 10)))
    with pytest.raises(AppointmentExpired):
        await cancel_appointment(
            appointment_id=row.id, reason="Unwell", actor="patient", actor_id=2,
            repo=repo, clock=clock,
        )


async def test_completed_cannot_be_cancelled(repo, clock):
    row = repo.seed(1, 2, to_utc(at(20, 10)), status="completed")
    with pytest.raises(InvalidTransition):
        await cancel_appointment(
            appointment_id=row.id, reason="Unwell", actor="patient", actor_id=2,
            repo=repo, clock=clock,
        )


async def test_cancel_inside_one_hour_allowed(repo, clock):
    # now 08:00, appointment at 08:30 - too soon to book, fine to cancel.
    row = repo.seed(1, 2, to_utc(at(19, 8, 30)))
    result = await cancel_appointment(
        appointment_id=row.id, reason="Unwell", actor="patient", actor_id=2,
        repo=repo, clock=clock,
    )
    assert result.status == "cancelled"
