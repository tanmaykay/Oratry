"""add durable email activation challenges

The table stores a SHA-256 digest of a one-time activation token, never the
token sent in email.  A partial unique index permits one outstanding signup
activation link per user while retaining consumed and invalidated evidence.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260919_04"
down_revision = "20260918_03"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "email_verification_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("purpose = 'signup_activation'", name="ck_email_verification_challenges_purpose"),
        sa.CheckConstraint("length(token_digest) = 64", name="ck_email_verification_challenges_token_digest_length"),
        sa.CheckConstraint("expires_at > created_at", name="ck_email_verification_challenges_expiry_after_creation"),
        sa.UniqueConstraint("token_digest", name="uq_email_verification_challenges_token_digest"),
    )
    op.create_index("ix_email_verification_challenges_user_id", "email_verification_challenges", ["user_id"])
    op.create_index("ix_email_verification_challenges_expires_at", "email_verification_challenges", ["expires_at"])
    op.create_index(
        "uq_email_verification_challenges_active_user_purpose",
        "email_verification_challenges",
        ["user_id", "purpose"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL AND invalidated_at IS NULL"),
        sqlite_where=sa.text("consumed_at IS NULL AND invalidated_at IS NULL"),
    )


def downgrade():
    op.drop_table("email_verification_challenges")
    op.drop_column("users", "email_verified_at")
