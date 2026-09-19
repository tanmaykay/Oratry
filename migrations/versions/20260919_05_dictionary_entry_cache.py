"""add provider-cached dictionary reference entries

Dictionary data is shared cache material, not user learning data.  User-owned
vocabulary records retain their entered word and optionally point to a cache
entry, allowing cache refreshes without mutating learner state.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260919_05"
down_revision = "20260919_04"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dictionary_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("normalized_term", sa.String(200), nullable=False),
        sa.Column("payload_version", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("language", "normalized_term", name="uq_dictionary_entries_language_normalized_term"),
        sa.CheckConstraint("length(trim(language)) > 0", name="ck_dictionary_entries_language_not_blank"),
        sa.CheckConstraint("length(trim(normalized_term)) > 0", name="ck_dictionary_entries_normalized_term_not_blank"),
        sa.CheckConstraint("length(trim(source)) > 0", name="ck_dictionary_entries_source_not_blank"),
        sa.CheckConstraint("expires_at IS NULL OR expires_at >= fetched_at", name="ck_dictionary_entries_expiry_after_fetch"),
    )
    op.create_index("ix_dictionary_entries_expires_at", "dictionary_entries", ["expires_at"])
    op.add_column("vocabulary_items", sa.Column("dictionary_entry_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_vocabulary_items_dictionary_entry_id",
        "vocabulary_items",
        "dictionary_entries",
        ["dictionary_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_vocabulary_items_dictionary_entry_id", "vocabulary_items", ["dictionary_entry_id"])


def downgrade():
    op.drop_index("ix_vocabulary_items_dictionary_entry_id", table_name="vocabulary_items")
    op.drop_constraint("fk_vocabulary_items_dictionary_entry_id", "vocabulary_items", type_="foreignkey")
    op.drop_column("vocabulary_items", "dictionary_entry_id")
    op.drop_index("ix_dictionary_entries_expires_at", table_name="dictionary_entries")
    op.drop_table("dictionary_entries")
