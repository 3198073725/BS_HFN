"""Attachment paper exams and manual grading.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("exam") as batch:
        batch.add_column(sa.Column("exam_type", sa.String(20), nullable=False, server_default="ONLINE"))
    with op.batch_alter_table("exam_record") as batch:
        for column in (
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("attachment", sa.String(500), nullable=True),
            sa.Column("attachment_name", sa.String(255), nullable=True),
            sa.Column("teacher_comment", sa.Text(), nullable=True),
            sa.Column("graded_time", sa.DateTime(), nullable=True),
        ):
            batch.add_column(column)


def downgrade():
    with op.batch_alter_table("exam_record") as batch:
        for name in ("graded_time", "teacher_comment", "attachment_name", "attachment", "content"):
            batch.drop_column(name)
    with op.batch_alter_table("exam") as batch:
        batch.drop_column("exam_type")
