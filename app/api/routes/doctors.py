"""Doctor availability lookup."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends

from app.api.deps import get_appointment_repo, get_clock, get_doctor_directory
from app.core.clock import Clock
from app.directories.base import DoctorDirectory
from app.repositories.appointments import AppointmentRepository
from app.schemas.appointments import AvailabilityResponse
from app.services import availability

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("/{doctor_id}/availability", response_model=AvailabilityResponse)
async def get_availability(
    doctor_id: uuid.UUID,
    date: date,
    repo: AppointmentRepository = Depends(get_appointment_repo),
    doctors: DoctorDirectory = Depends(get_doctor_directory),
    clock: Clock = Depends(get_clock),
) -> AvailabilityResponse:
    slots = await availability.generate_slots(
        doctor_id=doctor_id, day=date, repo=repo, doctors=doctors, clock=clock
    )
    return AvailabilityResponse(doctor_id=doctor_id, date=date.isoformat(), slots=slots)
