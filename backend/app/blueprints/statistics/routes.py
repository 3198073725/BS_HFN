from flask_jwt_extended import get_jwt_identity

from app.constants import UserRole
from app.extensions import db
from app.models import User
from app.services.statistics_service import (
    StatisticsPermissionDenied,
    get_overview,
    get_teacher_course_statistics,
)
from app.utils import error, roles_required, success
from . import statistics_bp


@statistics_bp.get("")
@roles_required(UserRole.STUDENT, UserRole.TEACHER, UserRole.ADMIN)
def overview():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    try:
        data = get_overview(user_id, user.role)
    except StatisticsPermissionDenied as exc:
        return error(str(exc), 403)
    return success(data)


@statistics_bp.get("/courses")
@roles_required(UserRole.TEACHER)
def teacher_courses():
    return success(get_teacher_course_statistics(int(get_jwt_identity())))
