"""rename pending status to reserved

WHY a data migration rather than editing 0001_initial: the initial revision has
already been applied to deployed databases (Render + Neon), so changing it would
leave those schemas out of sync with the code.

Revision ID: 0002_pending_to_reserved
Revises: 0001_initial
"""
from alembic import op

revision = "0002_pending_to_reserved"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop first: the old CHECK would reject 'reserved' while the data update runs.
    op.drop_constraint("ck_appointments_status", "appointments", type_="check")
    op.execute("UPDATE appointments SET status = 'reserved' WHERE status = 'pending'")
    op.alter_column("appointments", "status", server_default="reserved")
    op.create_check_constraint(
        "ck_appointments_status",
        "appointments",
        "status IN ('reserved','confirmed','rejected','cancelled','completed','no_show')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_appointments_status", "appointments", type_="check")
    op.execute("UPDATE appointments SET status = 'pending' WHERE status = 'reserved'")
    op.alter_column("appointments", "status", server_default="pending")
    op.create_check_constraint(
        "ck_appointments_status",
        "appointments",
        "status IN ('pending','confirmed','rejected','cancelled','completed','no_show')",
    )
