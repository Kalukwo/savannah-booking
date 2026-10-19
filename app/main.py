"""Application factory: routers, handlers, health message."""
from fastapi import FastAPI

from app.api.routes import appointments, doctors, patients
from app.core.errors import register_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clinic Appointments API",
        version="1.0.0",
        description="Booking for a five-doctor clinic. All times in the API are EAT (+03:00).",
    )
    register_error_handlers(app)
    app.include_router(appointments.router)
    app.include_router(doctors.router)
    app.include_router(patients.router)

    @app.get("/", tags=["meta"])
    async def root() -> dict:
        return {"message": "Clinic Appointments API. See /docs."}

    return app


app = create_app()
