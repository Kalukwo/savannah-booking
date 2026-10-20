from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, text
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Plain integers: the doctor and patient services own those records.
    doctor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    patient_id: Mapped[int] = mapped_column(Integer, nullable=False)
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
