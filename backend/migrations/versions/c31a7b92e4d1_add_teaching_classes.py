"""add teaching classes

Revision ID: c31a7b92e4d1
Revises: 5dd9d70a94f6
Create Date: 2026-09-12 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "c31a7b92e4d1"
down_revision = "5dd9d70a94f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teaching_class",
        sa.Column(
            "teacher_id",
            sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "id",
            sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["sys_user.id"],
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("teacher_id", "name", name="uk_teaching_class_teacher_name"),
    )
    with op.batch_alter_table("teaching_class", schema=None) as batch_op:
        batch_op.create_index("idx_teaching_class_teacher", ["teacher_id"], unique=False)

    op.create_table(
        "teaching_class_student",
        sa.Column(
            "class_id",
            sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
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
            ["student_id"],
            ["sys_user.id"],
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("class_id", "student_id", name="uk_teaching_class_student"),
    )
    with op.batch_alter_table("teaching_class_student", schema=None) as batch_op:
        batch_op.create_index(
            "idx_teaching_class_student_student",
            ["student_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("teaching_class_student", schema=None) as batch_op:
        batch_op.drop_index("idx_teaching_class_student_student")
    op.drop_table("teaching_class_student")
    with op.batch_alter_table("teaching_class", schema=None) as batch_op:
        batch_op.drop_index("idx_teaching_class_teacher")
    op.drop_table("teaching_class")
