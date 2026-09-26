"""add immutable challenge-target vocabulary observations

Revision ID: 20260924_10
Revises: 20260924_09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260924_10"
down_revision = "20260924_09"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vocabulary_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("vocabulary_item_id", sa.String(length=36), nullable=True),
        sa.Column("analysis_run_id", sa.String(length=36), nullable=False),
        sa.Column("normalized_word", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(normalized_word)) > 0", name="ck_vocabulary_observations_word_not_blank"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["vocabulary_item_id"], ["vocabulary_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_run_id", "normalized_word", name="uq_vocabulary_observations_run_word"),
    )
    op.create_index("ix_vocabulary_observations_user_id", "vocabulary_observations", ["user_id"])
    op.create_index("ix_vocabulary_observations_vocabulary_item_id", "vocabulary_observations", ["vocabulary_item_id"])
    op.create_index("ix_vocabulary_observations_analysis_run_id", "vocabulary_observations", ["analysis_run_id"])
    op.create_index("ix_vocabulary_observations_user_word_observed_at", "vocabulary_observations", ["user_id", "normalized_word", "observed_at"])


def downgrade():
    op.drop_index("ix_vocabulary_observations_user_word_observed_at", table_name="vocabulary_observations")
    op.drop_index("ix_vocabulary_observations_analysis_run_id", table_name="vocabulary_observations")
    op.drop_index("ix_vocabulary_observations_vocabulary_item_id", table_name="vocabulary_observations")
    op.drop_index("ix_vocabulary_observations_user_id", table_name="vocabulary_observations")
    op.drop_table("vocabulary_observations")
