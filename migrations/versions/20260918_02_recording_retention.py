"""add recording retention lifecycle"""
from alembic import op
import sqlalchemy as sa

revision="20260918_02"; down_revision="20260912_01"; branch_labels=None; depends_on=None

def upgrade():
    op.create_table("recordings", sa.Column("id", sa.String(36), primary_key=True), sa.Column("attempt_id", sa.String(36), sa.ForeignKey("attempts.id"), nullable=False), sa.Column("storage_provider", sa.String(40), nullable=False), sa.Column("object_key", sa.String(512), nullable=False), sa.Column("content_type", sa.String(100), nullable=False), sa.Column("byte_size", sa.Integer(), nullable=False), sa.Column("checksum_sha256", sa.String(64), nullable=False), sa.Column("retention_deadline", sa.DateTime(timezone=True)), sa.Column("deletion_status", sa.String(30), nullable=False), sa.Column("deleted_at", sa.DateTime(timezone=True)), sa.Column("deletion_error", sa.String(200)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("attempt_id"), sa.UniqueConstraint("object_key"))
    op.create_index("ix_recordings_retention_deadline", "recordings", ["retention_deadline"])

def downgrade():
    op.drop_table("recordings")
