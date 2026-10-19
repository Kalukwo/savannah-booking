"""Every appointment query lives here; services hold the rules."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import ACTIVE_STATUSES, Appointment


class AppointmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, appointment_id: int) -> Appointment | None:
        return await self.session.get(Appointment, appointment_id)

    async def get_for_update(self, appointment_id: int) -> Appointment | None:
        # WHY: the row lock serialises state changes on one appointment, so two
        # cancels or a cancel racing a reschedule cannot both succeed.
        stmt = select(Appointment).where(Appointment.id == appointment_id).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_active(self, doctor_id: int, start_time: datetime) -> Appointment | None:
        stmt = select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.start_time == start_time,
            Appointment.status.in_(ACTIVE_STATUSES),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_between(
        self, doctor_id: int, start: datetime, end: datetime
    ) -> list[Appointment]:
        stmt = select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.start_time >= start,
            Appointment.start_time < end,
            Appointment.status.in_(ACTIVE_STATUSES),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_upcoming_for_patient(
        self, patient_id: int, now: datetime
    ) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.start_time > now,
                Appointment.status.in_(ACTIVE_STATUSES),
            )
            .order_by(Appointment.start_time.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def add(self, appointment: Appointment) -> Appointment:
        self.session.add(appointment)
        return appointment

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, appointment) -> None:
        """Reload expired attributes inside the async context.

        WHY: updated_at carries server-side onupdate, so a flush expires it.
        Reading it later would trigger a lazy SELECT outside the greenlet and
        raise MissingGreenlet. Refreshing here keeps that IO where it belongs.
        """
        await self.session.refresh(appointment)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
