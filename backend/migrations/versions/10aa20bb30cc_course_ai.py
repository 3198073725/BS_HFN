"""增加视频字幕及课程 AI 总结。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '10aa20bb30cc'
down_revision = 'a7d9e2c4f6b8'
branch_labels = None
depends_on = None


def upgrade():
    identifier = sa.BigInteger().with_variant(sa.Integer(), 'sqlite').with_variant(mysql.BIGINT(unsigned=True), 'mysql')
    timestamps = lambda: [sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now())]
    op.create_table('video_subtitle',
        sa.Column('id', identifier, primary_key=True, autoincrement=True),
        sa.Column('video_id', identifier, sa.ForeignKey('video.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('source_hash', sa.String(64), nullable=False),
        sa.Column('segments', sa.JSON(), nullable=False),
        sa.Column('language', sa.String(30)), *timestamps())
    op.create_table('course_ai_summary',
        sa.Column('id', identifier, primary_key=True, autoincrement=True),
        sa.Column('course_id', identifier, sa.ForeignKey('course.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('task_id', sa.String(50)), sa.Column('content', sa.Text()),
        sa.Column('source_hash', sa.String(64)), sa.Column('error_message', sa.String(500)), *timestamps())


def downgrade():
    op.drop_table('course_ai_summary')
    op.drop_table('video_subtitle')
