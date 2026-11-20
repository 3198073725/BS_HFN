"""按视频保存 AI 总结，不将历史课程总结冒充为视频总结。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '30cc40dd50ee'
down_revision = '20bb30cc40dd'
branch_labels = None
depends_on = None


def upgrade():
    identifier = sa.BigInteger().with_variant(sa.Integer(), 'sqlite').with_variant(mysql.BIGINT(unsigned=True), 'mysql')
    op.create_table('video_ai_summary',
        sa.Column('id', identifier, primary_key=True, autoincrement=True),
        sa.Column('video_id', identifier, sa.ForeignKey('video.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('status', sa.String(30), nullable=False), sa.Column('task_id', sa.String(50)),
        sa.Column('content', sa.Text()), sa.Column('source_hash', sa.String(64)),
        sa.Column('error_message', sa.String(500)),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('progress_message', sa.String(200)),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))


def downgrade():
    op.drop_table('video_ai_summary')
