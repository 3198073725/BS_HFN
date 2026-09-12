import os

from werkzeug.security import generate_password_hash

from app import create_app
from app.constants import UserRole
from app.extensions import db
from app.models import CourseCategory, User


E2E_PASSWORD = "E2ePassword123!"
E2E_USERS = (
    {
        "username": "e2e_student",
        "real_name": "端测学生",
        "role": UserRole.STUDENT.value,
        "student_no": "E2ES001",
    },
    {
        "username": "e2e_teacher",
        "real_name": "端测教师",
        "role": UserRole.TEACHER.value,
        "teacher_no": "E2ET001",
    },
    {
        "username": "e2e_admin",
        "real_name": "端测管理员",
        "role": UserRole.ADMIN.value,
    },
)


def create_e2e_app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        password_hash = generate_password_hash(E2E_PASSWORD)
        db.session.add(CourseCategory(name="端测分类", sort_order=0))
        db.session.add_all(
            User(password_hash=password_hash, **user_data) for user_data in E2E_USERS
        )
        db.session.commit()
    return app


if __name__ == "__main__":
    create_e2e_app().run(
        host="127.0.0.1",
        port=int(os.getenv("E2E_BACKEND_PORT", "5100")),
        debug=False,
        use_reloader=False,
        threaded=False,
    )
