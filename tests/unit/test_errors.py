import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import (
    AppointmentNotFound,
    SlotTaken,
    register_error_handlers,
)


@pytest.fixture
def app():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/missing")
    async def missing():
        raise AppointmentNotFound()

    @app.get("/conflict")
    async def conflict():
        raise SlotTaken()

    return app


async def test_shape_for_domain_error(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/missing")
    assert response.status_code == 404
    assert response.json() == {"code": "APPOINTMENT_NOT_FOUND", "detail": "Appointment not found"}


async def test_shape_for_conflict(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/conflict")
    assert response.status_code == 409
    assert response.json()["code"] == "SLOT_TAKEN"
