"""create appointments and idempotency_keys

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.Column("cancelled_by", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','rejected','cancelled','completed','no_show')",
            name="ck_appointments_status",
        ),
        sa.CheckConstraint(
            "cancelled_by IS NULL OR cancelled_by IN ('patient','doctor')",
            name="ck_appointments_cancelled_by",
        ),
    )
    # Partial unique index: the database-level guarantee against double booking,
    # scoped to live appointments so cancelling or rejecting frees the slot.
    op.create_index(
        "uq_active_slot",
        "appointments",
        ["doctor_id", "start_time"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('cancelled','rejected')"),
    )
    op.create_index(
        "ix_appointments_patient_start", "appointments", ["patient_id", "start_time"]
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_index("ix_appointments_patient_start", table_name="appointments")
    op.drop_index("uq_active_slot", table_name="appointments")
    op.drop_table("appointments")
