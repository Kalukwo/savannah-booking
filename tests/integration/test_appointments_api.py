import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.directories.test_data.doctor_directory import fixed_uuid

pytestmark = pytest.mark.integration

DOC1 = str(fixed_uuid(1))
DOC2 = str(fixed_uuid(2))
PAT1 = str(fixed_uuid(101))
PAT2 = str(fixed_uuid(102))

# A UUID that is syntactically valid but belongs to no directory entry.
UNKNOWN_DOCTOR = "11111111-1111-4111-8111-111111111111"
UNKNOWN_APPOINTMENT = "22222222-2222-4222-8222-222222222222"


def day_at(day, hour, minute=0):
    return (day + timedelta(hours=hour, minutes=minute)).isoformat()


def payload(day, doctor=DOC1, patient=PAT1, hour=10, minute=0):
    return {
        "doctor_id": doctor,
        "patient_id": patient,
        "start_time": day_at(day, hour, minute),
    }


async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


async def test_double_booking_is_conflict(client, future_day):
    first = await client.post("/appointments", json=payload(future_day))
    assert first.status_code == 201
    assert first.json()["status"] == "reserved"

    second = await client.post("/appointments", json=payload(future_day))
    assert second.status_code == 409
    assert second.json()["code"] == "SLOT_TAKEN"


async def test_concurrent_booking_has_one_winner(client, future_day):
    body = payload(future_day, hour=11, minute=30)
    first, second = [
        client.post("/appointments", json=body),
        client.post("/appointments", json=body),
    ]
    responses = await asyncio.gather(first, second, return_exceptions=True)
    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 409]


async def test_same_instant_different_offsets_conflict(client, future_day):
    first = await client.post("/appointments", json=payload(future_day, hour=12))
    assert first.status_code == 201

    # 12:00 EAT == 09:00Z. Build the instant explicitly: future_day is already
    # midnight EAT, so adding 9 hours here would mean 06:00Z, not 09:00Z.
    utc_equivalent = datetime(
        future_day.year, future_day.month, future_day.day, 9, tzinfo=timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    second = await client.post(
        "/appointments",
        json={"doctor_id": DOC1, "patient_id": PAT2, "start_time": utc_equivalent},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "SLOT_TAKEN"


async def test_naive_time_is_eat(client, future_day):
    naive = (future_day + timedelta(hours=13)).strftime("%Y-%m-%dT%H:%M:%S")
    response = await client.post(
        "/appointments",
        json={"doctor_id": DOC1, "patient_id": PAT1, "start_time": naive},
    )
    assert response.status_code == 201
    returned = datetime.fromisoformat(response.json()["start_time"])
    assert returned.hour == 13


async def test_cancel_frees_slot_for_rebooking(client, future_day):
    created = await client.post("/appointments", json=payload(future_day, hour=14))
    appointment_id = created.json()["id"]

    cancelled = await client.patch(
        f"/appointments/{appointment_id}/cancel",
        json={"reason": "Unwell", "actor": "patient", "actor_id": PAT1},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    rebooked = await client.post(
        "/appointments", json=payload(future_day, patient=PAT2, hour=14)
    )
    assert rebooked.status_code == 201


async def test_reschedule_onto_taken_slot_keeps_original(client, future_day):
    first = await client.post("/appointments", json=payload(future_day, hour=15))
    await client.post("/appointments", json=payload(future_day, patient=PAT2, hour=15, minute=30))

    appointment_id = first.json()["id"]
    response = await client.patch(
        f"/appointments/{appointment_id}/reschedule",
        json={"patient_id": PAT1, "start_time": day_at(future_day, 15, 30)},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SLOT_TAKEN"

    listed = await client.get(f"/patients/{PAT1}/appointments")
    starts = [datetime.fromisoformat(row["start_time"]).hour for row in listed.json()]
    assert 15 in starts


async def test_full_flow(client, future_day):
    created = await client.post("/appointments", json=payload(future_day, hour=9))
    appointment_id = created.json()["id"]

    approved = await client.patch(
        f"/appointments/{appointment_id}/approve", json={"doctor_id": DOC1}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "confirmed"

    listed = await client.get(f"/patients/{PAT1}/appointments")
    rows = listed.json()
    assert rows and rows[0]["status"] == "confirmed"
    timestamps = [row["start_time"] for row in rows]
    assert timestamps == sorted(timestamps)


async def test_error_shapes(client):
    missing = await client.patch(
        f"/appointments/{UNKNOWN_APPOINTMENT}/approve", json={"doctor_id": DOC1}
    )
    assert missing.status_code == 404
    assert set(missing.json()) == {"code", "detail"}

    invalid = await client.post(
        "/appointments",
        json={"doctor_id": DOC1, "patient_id": PAT1, "start_time": "not-a-date"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"


async def test_unknown_doctor_is_not_found(client, future_day):
    response = await client.post(
        "/appointments", json=payload(future_day, doctor=UNKNOWN_DOCTOR)
    )
    assert response.status_code == 404
    assert response.json()["code"] == "DOCTOR_NOT_FOUND"


async def test_availability_excludes_booked_slot(client, future_day):
    booked = await client.post("/appointments", json=payload(future_day, hour=10))
    assert booked.status_code == 201

    response = await client.get(
        f"/doctors/{DOC1}/availability", params={"date": future_day.date().isoformat()}
    )
    assert response.status_code == 200
    # Compare full instants, not hours: 10:30 truncates to hour 10, so an
    # hour-level check could never pass while 10:30 was still free.
    booked_at = datetime.fromisoformat(booked.json()["start_time"])
    slots = [datetime.fromisoformat(s) for s in response.json()["slots"]]
    assert booked_at not in slots
    assert booked_at + timedelta(minutes=30) in slots


# --- idempotency (applied here so every request shares one session factory) ---

async def test_idempotent_replay_returns_same_appointment(client, future_day):
    body = payload(future_day, hour=16)
    headers = {"Idempotency-Key": "key-1"}

    first = await client.post("/appointments", json=body, headers=headers)
    second = await client.post("/appointments", json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_idempotent_key_reuse_with_different_body_conflicts(client, future_day):
    headers = {"Idempotency-Key": "key-2"}
    first = await client.post("/appointments", json=payload(future_day, hour=17), headers=headers)
    assert first.status_code in (201, 422)

    second = await client.post(
        "/appointments", json=payload(future_day, hour=16), headers=headers
    )
    if first.status_code == 201:
        assert second.status_code == 409
        assert second.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_no_header_behaves_normally(client, future_day):
    first = await client.post("/appointments", json=payload(future_day, hour=8))
    second = await client.post("/appointments", json=payload(future_day, hour=8))
    assert first.status_code == 201
    assert second.status_code == 409
