"""initial Oratry V1 schema"""
from alembic import op
from app.db import Base
from app import models  # noqa: F401
revision="20260912_01"; down_revision=None; branch_labels=None; depends_on=None
def upgrade(): Base.metadata.create_all(op.get_bind())
def downgrade(): Base.metadata.drop_all(op.get_bind())
