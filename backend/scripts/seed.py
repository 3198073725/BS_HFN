import os

from werkzeug.security import generate_password_hash

from app import create_app
from app.constants import UserRole
from app.extensions import db
from app.models import CourseCategory, User


CATEGORIES = ["计算机", "数学", "英语", "物理", "其他"]


def seed() -> None:
    app = create_app()
    with app.app_context():
        for index, name in enumerate(CATEGORIES):
            if CourseCategory.query.filter_by(name=name).first() is None:
                db.session.add(CourseCategory(name=name, sort_order=index))

        username = os.getenv("ADMIN_USERNAME", "admin")
        password = os.getenv("ADMIN_INITIAL_PASSWORD")
        if not password:
            raise RuntimeError("请先设置 ADMIN_INITIAL_PASSWORD，再执行初始化脚本")
        if User.query.filter_by(username=username).first() is None:
            db.session.add(
                User(
                    username=username,
                    password_hash=generate_password_hash(password),
                    real_name="系统管理员",
                    role=UserRole.ADMIN.value,
                )
            )
        db.session.commit()


if __name__ == "__main__":
    seed()
