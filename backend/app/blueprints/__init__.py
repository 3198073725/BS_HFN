from flask import Flask

from .admin import admin_bp
from .auth import auth_bp
from .courses import courses_bp
from .exams import exams_bp
from .homework import homework_bp
from .learning import learning_bp
from .notices import notices_bp
from .questions import questions_bp
from .statistics import statistics_bp
from .system import system_bp
from .users import users_bp
from .videos import videos_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(system_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(courses_bp, url_prefix="/api/courses")
    app.register_blueprint(videos_bp, url_prefix="/api/videos")
    app.register_blueprint(learning_bp, url_prefix="/api/learning")
    app.register_blueprint(notices_bp, url_prefix="/api/notices")
    app.register_blueprint(questions_bp, url_prefix="/api/questions")
    app.register_blueprint(homework_bp, url_prefix="/api/homeworks")
    app.register_blueprint(exams_bp, url_prefix="/api/exams")
    app.register_blueprint(statistics_bp, url_prefix="/api/statistics")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
