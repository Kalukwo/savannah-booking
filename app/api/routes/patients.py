"""Patient-facing reads."""
from fastapi import APIRouter, Depends

from app.api.deps import get_appointment_repo, get_clock, get_patient_directory
from app.core.clock import Clock
from app.directories.base import PatientDirectory
from app.repositories.appointments import AppointmentRepository
from app.schemas.appointments import AppointmentResponse
from app.services import patients as patient_service

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/{patient_id}/appointments", response_model=list[AppointmentResponse])
async def list_patient_appointments(
    patient_id: int,
    repo: AppointmentRepository = Depends(get_appointment_repo),
    patients: PatientDirectory = Depends(get_patient_directory),
    clock: Clock = Depends(get_clock),
) -> list[AppointmentResponse]:
    rows = await patient_service.upcoming_for_patient(
        patient_id=patient_id, repo=repo, patients=patients, clock=clock
    )
    return [AppointmentResponse.from_model(r) for r in rows]
