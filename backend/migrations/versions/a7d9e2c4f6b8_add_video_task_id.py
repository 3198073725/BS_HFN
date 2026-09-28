"""Track asynchronous video jobs so administrators can terminate them."""

from alembic import op
import sqlalchemy as sa


revision = "a7d9e2c4f6b8"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("video")}
    indexes = {item["name"] for item in inspector.get_indexes("video")}
    if "task_id" not in columns:
        with op.batch_alter_table("video") as batch_op:
            batch_op.add_column(sa.Column("task_id", sa.String(length=50), nullable=True))
    if "ix_video_task_id" not in indexes:
        with op.batch_alter_table("video") as batch_op:
            batch_op.create_index("ix_video_task_id", ["task_id"], unique=False)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("video")}
    indexes = {item["name"] for item in inspector.get_indexes("video")}
    if "ix_video_task_id" in indexes:
        with op.batch_alter_table("video") as batch_op:
            batch_op.drop_index("ix_video_task_id")
    if "task_id" in columns:
        with op.batch_alter_table("video") as batch_op:
            batch_op.drop_column("task_id")
