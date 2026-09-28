"""Apply this additive local upgrade only after a verified SQL backup."""
from pathlib import Path

from flask_migrate import upgrade
from sqlalchemy import inspect, text
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app import create_app
from app.extensions import db
from scripts.seed_demo import backup_mysql


def main():
    app = create_app('development')
    with app.app_context():
        if db.engine.dialect.name != 'mysql':
            raise RuntimeError('此脚本仅升级已初始化的本地MySQL开发库')
        revision = db.session.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        target = 'f6a7b8c9d0e1'
        if revision == target:
            print('数据库已是本次版本，无需重复升级')
            return
        if revision != 'e5f6a7b8c9d0':
            raise RuntimeError('数据库版本不是预期前置版本，停止升级，请先核对迁移')
        # Compare existing table counts, not private row contents or credentials.
        names = [name for name in inspect(db.engine).get_table_names() if name != 'alembic_version']
        quoted = db.engine.dialect.identifier_preparer.quote
        before = {name: db.session.execute(text(f'SELECT COUNT(*) FROM {quoted(name)}')).scalar_one() for name in names}
        learning_before = tuple(db.session.execute(text('SELECT COALESCE(SUM(watch_duration),0), COALESCE(SUM(progress),0) FROM learning_record')).one())
        db.session.remove()
        destination = backup_mysql(app)
        print(f'SQL备份已保存：{destination}')
        upgrade(directory=str(Path(__file__).resolve().parents[1] / 'migrations'), revision=target)
        after = {name: db.session.execute(text(f'SELECT COUNT(*) FROM {quoted(name)}')).scalar_one() for name in names}
        learning_after = tuple(db.session.execute(text('SELECT COALESCE(SUM(watch_duration),0), COALESCE(SUM(progress),0) FROM learning_record')).one())
        if before != after or learning_before != learning_after:
            raise RuntimeError('升级后数据核对不一致，请保留备份并停止后续操作；不自动覆盖恢复')
        with db.engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection, opts={'compare_type': True}), db.metadata)
        if differences:
            raise RuntimeError('升级后存在模型差异，请检查迁移；不自动修改额外表')
        print(f'升级至{target}完成；{len(names)}张原有表数量及学习累计值核对一致，模型无漂移')


if __name__ == '__main__':
    main()
