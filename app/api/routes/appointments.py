"""Appointment endpoints. Shape in, one service call, shape out."""
from fastapi import APIRouter, Depends, Header, Response, status

from app.api.deps import (
    get_appointment_repo,
    get_clock,
    get_doctor_directory,
    get_idempotency_store,
    get_patient_directory,
)
from app.core.clock import Clock
from app.core.errors import ValidationError
from app.directories.base import DoctorDirectory, PatientDirectory
from app.repositories.appointments import AppointmentRepository
from app.schemas.appointments import (
    AppointmentCreate,
    AppointmentResponse,
    CancelRequest,
    DoctorActionRequest,
    RescheduleRequest,
)
from app.services import booking, cancel, idempotency, lifecycle, reschedule

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _response(appointment) -> AppointmentResponse:
    return AppointmentResponse.from_model(appointment)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AppointmentResponse)
async def create_appointment(
    payload: AppointmentCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    repo: AppointmentRepository = Depends(get_appointment_repo),
    doctors: DoctorDirectory = Depends(get_doctor_directory),
    patients: PatientDirectory = Depends(get_patient_directory),
    store=Depends(get_idempotency_store),
    clock: Clock = Depends(get_clock),
) -> AppointmentResponse:
    deadline = clock()

    # Only a supplied key opts into replay behaviour; absent means plain booking.
    if idempotency_key is not None:
        replay = await idempotency.claim_key(
            store, idempotency_key, payload.model_dump(), deadline
        )
        if replay is not None:
            response.status_code = replay["status"] or 200
            return AppointmentResponse.model_validate(replay["body"])

    appointment = await booking.book_appointment(
        doctor_id=payload.doctor_id,
        patient_id=payload.patient_id,
        start_time=payload.start_time,
        repo=repo,
        doctors=doctors,
        patients=patients,
        clock=clock,
    )
    body = _response(appointment)

    if idempotency_key is not None:
        await store.store(idempotency_key, 201, body.model_dump(mode="json"))

    # Commit after the key row is written so both land together.
    await repo.commit()
    return body


@router.patch("/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_appointment(
    appointment_id: int,
    payload: CancelRequest,
    repo: AppointmentRepository = Depends(get_appointment_repo),
    clock: Clock = Depends(get_clock),
) -> AppointmentResponse:
    reason = payload.reason.strip()
    if not reason:
        raise ValidationError("reason: must not be blank")
    appointment = await cancel.cancel_appointment(
        appointment_id=appointment_id,
        reason=reason,
        actor=payload.actor,
        actor_id=payload.actor_id,
        repo=repo,
        clock=clock,
    )
    await repo.refresh(appointment)
    body = _response(appointment)
    await repo.commit()
    return body


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentResponse)
async def reschedule_appointment(
    appointment_id: int,
    payload: RescheduleRequest,
    repo: AppointmentRepository = Depends(get_appointment_repo),
    doctors: DoctorDirectory = Depends(get_doctor_directory),
    clock: Clock = Depends(get_clock),
) -> AppointmentResponse:
    appointment = await reschedule.reschedule_appointment(
        appointment_id=appointment_id,
        patient_id=payload.patient_id,
        start_time=payload.start_time,
        repo=repo,
        doctors=doctors,
        clock=clock,
    )
    await repo.refresh(appointment)
    body = _response(appointment)
    await repo.commit()
    return body


@router.patch("/{appointment_id}/approve", response_model=AppointmentResponse)
async def approve_appointment(
    appointment_id: int,
    payload: DoctorActionRequest,
    repo: AppointmentRepository = Depends(get_appointment_repo),
    clock: Clock = Depends(get_clock),
) -> AppointmentResponse:
    appointment = await lifecycle.approve(
        appointment_id=appointment_id, doctor_id=payload.doctor_id, repo=repo, clock=clock
    )
    await repo.refresh(appointment)
    body = _response(appointment)
    await repo.commit()
    return body


@router.patch("/{appointment_id}/reject", response_model=AppointmentResponse)
async def reject_appointment(
    appointment_id: int,
    payload: DoctorActionRequest,
    repo: AppointmentRepository = Depends(get_appointment_repo),
    clock: Clock = Depends(get_clock),
) -> AppointmentResponse:
    appointment = await lifecycle.reject(
        appointment_id=appointment_id, doctor_id=payload.doctor_id, repo=repo, clock=clock
    )
    await repo.refresh(appointment)
    body = _response(appointment)
    await repo.commit()
    return body


@router.patch("/{appointment_id}/complete", response_model=AppointmentResponse)
async def complete_appointment(
    appointment_id: int,
    payload: DoctorActionRequest,
    repo: AppointmentRepository = Depends(get_appointment_repo),
    clock: Clock = Depends(get_clock),
) -> AppointmentResponse:
    appointment = await lifecycle.complete(
        appointment_id=appointment_id, doctor_id=payload.doctor_id, repo=repo, clock=clock
    )
    await repo.refresh(appointment)
    body = _response(appointment)
    await repo.commit()
    return body


@router.patch("/{appointment_id}/no-show", response_model=AppointmentResponse)
async def no_show_appointment(
    appointment_id: int,
    payload: DoctorActionRequest,
    repo: AppointmentRepository = Depends(get_appointment_repo),
    clock: Clock = Depends(get_clock),
) -> AppointmentResponse:
    appointment = await lifecycle.no_show(
        appointment_id=appointment_id, doctor_id=payload.doctor_id, repo=repo, clock=clock
    )
    await repo.refresh(appointment)
    body = _response(appointment)
    await repo.commit()
    return body
