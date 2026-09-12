"""add teaching class courses

Revision ID: f4a2b9d7e6c1
Revises: c31a7b92e4d1
Create Date: 2026-09-12 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "f4a2b9d7e6c1"
down_revision = "c31a7b92e4d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teaching_class_course",
        sa.Column(
            "class_id",
            sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "id",
            sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
            autoincrement=True,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["teaching_class.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["course.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("class_id", "course_id", name="uk_teaching_class_course"),
    )
    with op.batch_alter_table("teaching_class_course", schema=None) as batch_op:
        batch_op.create_index(
            "idx_teaching_class_course_course",
            ["course_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("teaching_class_course", schema=None) as batch_op:
        batch_op.drop_index("idx_teaching_class_course_course")
    op.drop_table("teaching_class_course")
