"""add admin audit logs

Revision ID: 8b7c6d5e4f32
Revises: f4a2b9d7e6c1
Create Date: 2026-09-12 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "8b7c6d5e4f32"
down_revision = "f4a2b9d7e6c1"
branch_labels = None
depends_on = None


def upgrade():
    unsigned_bigint = sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql")
    op.create_table(
        "admin_audit_log",
        sa.Column("admin_id", unsigned_bigint, nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", unsigned_bigint, nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", unsigned_bigint, autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["sys_user.id"],
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("admin_audit_log", schema=None) as batch_op:
        batch_op.create_index(
            "idx_admin_audit_action_time", ["action", "created_at"], unique=False
        )
        batch_op.create_index(
            "idx_admin_audit_admin_time", ["admin_id", "created_at"], unique=False
        )
        batch_op.create_index(
            "idx_admin_audit_resource", ["resource_type", "resource_id"], unique=False
        )


def downgrade():
    with op.batch_alter_table("admin_audit_log", schema=None) as batch_op:
        batch_op.drop_index("idx_admin_audit_resource")
        batch_op.drop_index("idx_admin_audit_admin_time")
        batch_op.drop_index("idx_admin_audit_action_time")
    op.drop_table("admin_audit_log")
