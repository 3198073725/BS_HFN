"""Add teacher exam attachments.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("exam") as batch:
        batch.add_column(sa.Column("attachment", sa.String(500), nullable=True))
        batch.add_column(sa.Column("attachment_name", sa.String(255), nullable=True))


def downgrade():
    with op.batch_alter_table("exam") as batch:
        batch.drop_column("attachment_name")
        batch.drop_column("attachment")
