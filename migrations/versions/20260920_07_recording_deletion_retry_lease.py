"""add durable recording deletion retry and lease state

Raw audio remains governed by the existing retention deadline.  These additive
columns only make server-side deletion claims restart-safe and retryable across
workers; no recording bytes or provider response data are stored here.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260920_07"
down_revision = "20260920_06"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "recordings",
        sa.Column(
            "deletion_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "recordings",
        sa.Column("deletion_available_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recordings",
        sa.Column("deletion_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_recordings_deletion_attempt_count_nonnegative",
        "recordings",
        "deletion_attempt_count >= 0",
    )
    # Existing scheduled rows remain eligible at their pre-existing deadline.
    # This preserves their retention decision while making them claimable under
    # the new durable worker contract.
    op.execute(
        """
        UPDATE recordings
        SET deletion_available_at = retention_deadline
        WHERE deletion_status = 'scheduled'
          AND deletion_available_at IS NULL
          AND retention_deadline IS NOT NULL
        """
    )
    op.create_index(
        "ix_recordings_deletion_claim",
        "recordings",
        ["deletion_status", "deletion_available_at", "retention_deadline"],
    )


def downgrade():
    op.drop_index("ix_recordings_deletion_claim", table_name="recordings")
    op.drop_constraint(
        "ck_recordings_deletion_attempt_count_nonnegative",
        "recordings",
        type_="check",
    )
    op.drop_column("recordings", "deletion_lease_expires_at")
    op.drop_column("recordings", "deletion_available_at")
    op.drop_column("recordings", "deletion_attempt_count")
