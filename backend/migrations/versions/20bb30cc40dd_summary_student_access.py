"""允许按课程设置 AI 总结向所有学生开放。"""
from alembic import op
import sqlalchemy as sa

revision = '20bb30cc40dd'
down_revision = '10aa20bb30cc'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('course_ai_summary') as batch:
        batch.add_column(sa.Column('open_to_students', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('course_ai_summary') as batch:
        batch.drop_column('open_to_students')
