"""appointments id, doctor_id and patient_id to UUID

The initial revisions are already applied to deployed databases, so this is a
new revision rather than an edit of 0001/0002.

Integer ids cannot be cast to uuid, and doctor/patient ids must match the
external services that own them, so existing rows are discarded. The table is
empty in every environment this runs in.

Revision ID: 0003_uuid_ids
Revises: 0002_pending_to_reserved
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_uuid_ids"
down_revision = "0002_pending_to_reserved"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No integer -> uuid cast exists; the rows are disposable test data.
    op.execute("TRUNCATE appointments")

    op.drop_index("uq_active_slot", table_name="appointments")
    op.drop_index("ix_appointments_patient_start", table_name="appointments")

    op.drop_column("appointments", "id")
    op.drop_column("appointments", "doctor_id")
    op.drop_column("appointments", "patient_id")

    op.add_column("appointments", sa.Column("id", sa.Uuid(), primary_key=True))
    op.add_column("appointments", sa.Column("doctor_id", sa.Uuid(), nullable=False))
    op.add_column("appointments", sa.Column("patient_id", sa.Uuid(), nullable=False))

    # Rebuilt on the new column types: this partial unique index is the
    # database-level guard against double booking.
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


def downgrade() -> None:
    op.execute("TRUNCATE appointments")

    op.drop_index("uq_active_slot", table_name="appointments")
    op.drop_index("ix_appointments_patient_start", table_name="appointments")

    op.drop_column("appointments", "id")
    op.drop_column("appointments", "doctor_id")
    op.drop_column("appointments", "patient_id")

    op.add_column("appointments", sa.Column("id", sa.Integer(), primary_key=True))
    op.add_column("appointments", sa.Column("doctor_id", sa.Integer(), nullable=False))
    op.add_column("appointments", sa.Column("patient_id", sa.Integer(), nullable=False))

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
