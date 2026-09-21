"""add durable analysis job delivery table

The table is an additive outbox-style delivery record.  It does not replace
the prototype in-memory queue until worker integration explicitly adopts it.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260920_06"
down_revision = "20260919_05"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("attempts.id"), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("stage_version", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_key", name="uq_analysis_jobs_event_key"),
        sa.UniqueConstraint("attempt_id", "stage", "stage_version", name="uq_analysis_jobs_attempt_stage_version"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_analysis_jobs_attempt_count_nonnegative"),
        sa.CheckConstraint("status IN ('queued', 'leased', 'completed', 'failed')", name="ck_analysis_jobs_status"),
        sa.CheckConstraint("lease_expires_at IS NULL OR lease_owner IS NOT NULL", name="ck_analysis_jobs_lease_owner_required"),
        sa.CheckConstraint("completed_at IS NULL OR status IN ('completed', 'failed')", name="ck_analysis_jobs_terminal_status_for_completion"),
    )
    op.create_index("ix_analysis_jobs_attempt_id", "analysis_jobs", ["attempt_id"])
    op.create_index("ix_analysis_jobs_claim", "analysis_jobs", ["status", "available_at", "created_at"])
    op.create_index("ix_analysis_jobs_lease_expires_at", "analysis_jobs", ["lease_expires_at"])


def downgrade():
    op.drop_index("ix_analysis_jobs_lease_expires_at", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_claim", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_attempt_id", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
