"""add notifications

Revision ID: 9c8d7e6f5a43
Revises: 8b7c6d5e4f32
Create Date: 2026-09-12 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "9c8d7e6f5a43"
down_revision = "8b7c6d5e4f32"
branch_labels = None
depends_on = None


def upgrade():
    unsigned_bigint = sa.BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql")
    op.create_table(
        "notification",
        sa.Column("recipient_id", unsigned_bigint, nullable=False),
        sa.Column("sender_id", unsigned_bigint, nullable=True),
        sa.Column("category", sa.String(length=50), server_default="SYSTEM", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=255), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", unsigned_bigint, autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(["recipient_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("notification", schema=None) as batch_op:
        batch_op.create_index("idx_notification_recipient_read", ["recipient_id", "read_at"], unique=False)
        batch_op.create_index("idx_notification_recipient_time", ["recipient_id", "created_at"], unique=False)


def downgrade():
    with op.batch_alter_table("notification", schema=None) as batch_op:
        batch_op.drop_index("idx_notification_recipient_time")
        batch_op.drop_index("idx_notification_recipient_read")
    op.drop_table("notification")
