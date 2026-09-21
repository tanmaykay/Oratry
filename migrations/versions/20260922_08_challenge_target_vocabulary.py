"""persist versioned challenge-owned vocabulary targets

Challenge targets are immutable curriculum context for deterministic transcript
coverage. Existing challenge versions receive an empty list rather than an
invented target set.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260922_08"
down_revision = "20260920_07"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "challenges",
        sa.Column("target_vocabulary", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade():
    op.drop_column("challenges", "target_vocabulary")
