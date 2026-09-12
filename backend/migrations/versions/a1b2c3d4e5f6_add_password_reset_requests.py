"""add password reset requests

Revision ID: a1b2c3d4e5f6
Revises: 9c8d7e6f5a43
Create Date: 2026-09-12 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "a1b2c3d4e5f6"
down_revision = "9c8d7e6f5a43"
branch_labels = None
depends_on = None


def upgrade():
    unsigned_bigint = sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql")
    op.create_table(
        "password_reset_request",
        sa.Column("student_id", unsigned_bigint, nullable=False),
        sa.Column("requested_password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("reviewer_id", unsigned_bigint, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("id", unsigned_bigint, autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["reviewer_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("password_reset_request", schema=None) as batch_op:
        batch_op.create_index("idx_password_reset_status_expiry", ["status", "expires_at"], unique=False)
        batch_op.create_index("idx_password_reset_student_status", ["student_id", "status"], unique=False)


def downgrade():
    with op.batch_alter_table("password_reset_request", schema=None) as batch_op:
        batch_op.drop_index("idx_password_reset_student_status")
        batch_op.drop_index("idx_password_reset_status_expiry")
    op.drop_table("password_reset_request")
