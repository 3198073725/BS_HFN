"""Durable progress request deduplication; no existing learning data is changed."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    identifier = sa.BigInteger().with_variant(sa.Integer(), "sqlite").with_variant(mysql.BIGINT(unsigned=True), "mysql")
    op.create_table("learning_progress_receipt",
        sa.Column("id", identifier, primary_key=True, autoincrement=True),
        sa.Column("student_id", identifier, sa.ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("video_id", identifier, sa.ForeignKey("video.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(100).with_variant(mysql.VARCHAR(100, charset="ascii", collation="ascii_bin"), "mysql"), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("student_id", "request_id", name="uk_progress_receipt_request"))


def downgrade():
    op.drop_table("learning_progress_receipt")
