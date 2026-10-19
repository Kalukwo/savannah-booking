"""Reading a patient's upcoming appointments."""
from app.core.clock import Clock
from app.core.errors import PatientNotFound
from app.directories.base import PatientDirectory
from app.models.appointment import Appointment
from app.repositories.appointments import AppointmentRepository


async def upcoming_for_patient(
    *, patient_id: int, repo: AppointmentRepository, patients: PatientDirectory, clock: Clock
) -> list[Appointment]:
    if not await patients.exists(patient_id):
        raise PatientNotFound()
    return await repo.list_upcoming_for_patient(patient_id, clock())
