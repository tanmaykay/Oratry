"""add reversible learner review visibility

Hidden attempts remain immutable learning evidence and do not affect baseline
completion or skill projections. The flag only removes an item from learner
progress and review surfaces.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260924_09"
down_revision = "20260922_08"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("attempts", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_attempts_hidden_at", "attempts", ["hidden_at"])


def downgrade():
    op.drop_index("ix_attempts_hidden_at", table_name="attempts")
    op.drop_column("attempts", "hidden_at")
