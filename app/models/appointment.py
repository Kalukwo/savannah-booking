import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ACTIVE_STATUSES = ("reserved", "confirmed")
SLOT_FREEING_STATUSES = ("cancelled", "rejected")
ALL_STATUSES = (
    "reserved",
    "confirmed",
    "rejected",
    "cancelled",
    "completed",
    "no_show",
)


class Appointment(Base):
    __tablename__ = "appointments"

    # Generated in Python, not by the database, so the id is known before flush
    # and the row can be returned without a second round trip.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # UUIDs, not integers: the doctor and patient services own those records and
    # identify them by UUID. Still plain columns with no foreign key - the rows
    # live in another service's database.
    doctor_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved")
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved','confirmed','rejected','cancelled','completed','no_show')",
            name="ck_appointments_status",
        ),
        CheckConstraint(
            "cancelled_by IS NULL OR cancelled_by IN ('patient','doctor')",
            name="ck_appointments_cancelled_by",
        ),
        # WHY: the final guard against double booking, enforced by the database
        # so concurrent requests cannot race past application checks. Partial,
        # so cancelling or rejecting frees the slot for someone else.
        Index(
            "uq_active_slot",
            "doctor_id",
            "start_time",
            unique=True,
            postgresql_where=text("status NOT IN ('cancelled','rejected')"),
        ),
        Index("ix_appointments_patient_start", "patient_id", "start_time"),
    )
