"""add verified external identities and one-time OAuth browser handoffs

Revision ID: 20260924_12
Revises: 20260924_11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260924_12"
down_revision = "20260924_11"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "subject", name="uq_external_identities_provider_subject"),
    )
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"])
    op.create_table(
        "oauth_login_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(code_digest) = 64", name="ck_oauth_login_codes_digest_length"),
        sa.CheckConstraint("expires_at > created_at", name="ck_oauth_login_codes_expiry_after_creation"),
        sa.UniqueConstraint("code_digest", name="uq_oauth_login_codes_code_digest"),
    )
    op.create_index("ix_oauth_login_codes_user_id", "oauth_login_codes", ["user_id"])
    op.create_index("ix_oauth_login_codes_expires_at", "oauth_login_codes", ["expires_at"])


def downgrade():
    op.drop_table("oauth_login_codes")
    op.drop_table("external_identities")
