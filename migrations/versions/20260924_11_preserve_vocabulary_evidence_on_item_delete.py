"""retain immutable vocabulary evidence when a Word Bank item is removed

Revision ID: 20260924_11
Revises: 20260924_10
"""

from alembic import op


revision = "20260924_11"
down_revision = "20260924_10"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "vocabulary_observations_vocabulary_item_id_fkey",
        "vocabulary_observations",
        type_="foreignkey",
    )
    op.alter_column("vocabulary_observations", "vocabulary_item_id", nullable=True)
    op.create_foreign_key(
        "fk_vocabulary_observations_vocabulary_item_id",
        "vocabulary_observations",
        "vocabulary_items",
        ["vocabulary_item_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_vocabulary_observations_vocabulary_item_id", "vocabulary_observations", type_="foreignkey")
    # Revision 20260924_10 required this link. A rollback therefore cannot
    # represent evidence deliberately retained after its Word Bank item was
    # deleted; discard only those incompatible observations before restoring
    # the old invariant.
    op.execute("DELETE FROM vocabulary_observations WHERE vocabulary_item_id IS NULL")
    op.alter_column("vocabulary_observations", "vocabulary_item_id", nullable=False)
    op.create_foreign_key(
        "vocabulary_observations_vocabulary_item_id_fkey",
        "vocabulary_observations",
        "vocabulary_items",
        ["vocabulary_item_id"],
        ["id"],
    )
