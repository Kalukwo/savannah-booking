"""Idempotency-Key handling for POST /appointments.

WHY: a client that retries after a timeout must not double book. The key
row is inserted in the same transaction as the booking, so either both are
committed or neither is.
"""
import hashlib
import json
import uuid
from datetime import datetime

from app.core.errors import IdempotencyKeyReused
from app.core.timezone import to_utc


def request_hash(body: dict) -> str:
    """Canonical hash: key order independent, start_time normalised to UTC."""
    canonical = dict(body)
    start = canonical.get("start_time")
    if start is not None:
        if isinstance(start, str):
            start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        canonical["start_time"] = to_utc(start).isoformat()
    # UUIDs (doctor_id, patient_id) are not JSON serialisable; hash their text
    # form so the same logical request always produces the same digest.
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


async def claim_key(store, key: str, body: dict, now: datetime) -> dict | None:
    """Return the stored response to replay, or None if we should proceed."""
    digest = request_hash(body)
    claimed, existing = await store.claim(key, digest, now)
    if claimed:
        return None
    if existing["hash"] != digest:
        raise IdempotencyKeyReused()
    return existing
