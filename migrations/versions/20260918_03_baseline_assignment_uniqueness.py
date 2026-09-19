"""enforce unique baseline assignments per user

The fixed baseline is a single sequence.  These partial unique indexes make
the create-or-return operation safe when two requests race, while allowing
unlimited ordinary/recommended assignments.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260918_03"
down_revision = "20260918_02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "uq_challenge_assignments_baseline_user_sequence",
        "challenge_assignments",
        ["user_id", "sequence"],
        unique=True,
        postgresql_where=sa.text("reason = 'baseline'"),
        sqlite_where=sa.text("reason = 'baseline'"),
    )
    op.create_index(
        "uq_challenge_assignments_baseline_user_challenge",
        "challenge_assignments",
        ["user_id", "challenge_id"],
        unique=True,
        postgresql_where=sa.text("reason = 'baseline'"),
        sqlite_where=sa.text("reason = 'baseline'"),
    )


def downgrade():
    op.drop_index(
        "uq_challenge_assignments_baseline_user_challenge",
        table_name="challenge_assignments",
    )
    op.drop_index(
        "uq_challenge_assignments_baseline_user_sequence",
        table_name="challenge_assignments",
    )
