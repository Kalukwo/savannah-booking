"""Stand-in for the patient service - ids 1-5 exist."""

_PATIENT_IDS = {1, 2, 3, 4, 5}


class PatientTestDataDirectory:
    async def exists(self, patient_id: int) -> bool:
        return patient_id in _PATIENT_IDS
