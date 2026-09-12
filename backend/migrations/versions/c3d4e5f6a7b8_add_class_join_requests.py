"""add class join requests

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-12 22:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    unsigned_bigint = sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql")
    op.create_table(
        "teaching_class_join_request",
        sa.Column("class_id", unsigned_bigint, nullable=False),
        sa.Column("student_id", unsigned_bigint, nullable=False),
        sa.Column("source_course_id", unsigned_bigint, nullable=True),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("reviewer_id", unsigned_bigint, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("id", unsigned_bigint, autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["class_id"], ["teaching_class.id"], onupdate="CASCADE", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_course_id"], ["course.id"], onupdate="CASCADE", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("class_id", "student_id", name="uk_class_join_request_student"),
    )
    with op.batch_alter_table("teaching_class_join_request", schema=None) as batch_op:
        batch_op.create_index("idx_class_join_request_class_status", ["class_id", "status"], unique=False)
        batch_op.create_index("idx_class_join_request_student_status", ["student_id", "status"], unique=False)


def downgrade():
    with op.batch_alter_table("teaching_class_join_request", schema=None) as batch_op:
        batch_op.drop_index("idx_class_join_request_student_status")
        batch_op.drop_index("idx_class_join_request_class_status")
    op.drop_table("teaching_class_join_request")
