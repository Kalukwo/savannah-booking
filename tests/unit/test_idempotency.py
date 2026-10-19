import pytest

from app.core.errors import IdempotencyKeyReused
from app.services.idempotency import claim_key, request_hash


class FakeStore:
    def __init__(self):
        self.rows = {}

    async def claim(self, key, digest, now):
        if key in self.rows:
            row = self.rows[key]
            return False, {"hash": row["hash"], "status": 201, "body": {"id": 1}}
        self.rows[key] = {"hash": digest}
        return True, None


def test_hash_is_offset_independent():
    a = request_hash({"doctor_id": 1, "patient_id": 1, "start_time": "2026-10-20T10:00:00+03:00"})
    b = request_hash({"doctor_id": 1, "patient_id": 1, "start_time": "2026-10-20T07:00:00Z"})
    assert a == b


def test_hash_changes_with_body():
    a = request_hash({"doctor_id": 1, "patient_id": 1, "start_time": "2026-10-20T10:00:00+03:00"})
    b = request_hash({"doctor_id": 2, "patient_id": 1, "start_time": "2026-10-20T10:00:00+03:00"})
    assert a != b


async def test_first_claim_proceeds():
    store = FakeStore()
    result = await claim_key(store, "k1", {"doctor_id": 1}, None)
    assert result is None


async def test_same_body_replays():
    store = FakeStore()
    body = {"doctor_id": 1}
    await claim_key(store, "k1", body, None)
    replay = await claim_key(store, "k1", body, None)
    assert replay["status"] == 201


async def test_different_body_rejected():
    store = FakeStore()
    await claim_key(store, "k1", {"doctor_id": 1}, None)
    with pytest.raises(IdempotencyKeyReused):
        await claim_key(store, "k1", {"doctor_id": 2}, None)
