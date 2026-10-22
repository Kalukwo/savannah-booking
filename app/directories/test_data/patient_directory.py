"""Stand-in for the patient service - three patients exist.

WHY: patients are owned by the patient service, not by this one. There is no
patient table and no seed script; the boundary is a Protocol and this in-code
implementation stands in for the real HTTP client.

The UUIDs are FIXED and hand-written (not uuid4) so they stay stable across
runs and are documented in the README.
"""
import uuid


def patient_id(n: int) -> uuid.UUID:
    """Readable, deterministic UUID: 00000000-0000-4000-8000-00000000010n."""
    return uuid.UUID(f"00000000-0000-4000-8000-{100 + n:012d}")


PATIENT_IDS: set[uuid.UUID] = {patient_id(n) for n in range(1, 4)}


class PatientTestDataDirectory:
    async def exists(self, patient_id: uuid.UUID) -> bool:
        return patient_id in PATIENT_IDS
