from sqlalchemy import or_

from app.constants import UserRole
from app.extensions import db
from app.models import User


class AdminNotFound(ValueError):
    pass


class AdminConflict(ValueError):
    pass


def list_users(role: str | None = None, status: bool | None = None, keyword: str | None = None) -> list[dict]:
    statement = db.select(User)
    if role:
        statement = statement.where(User.role == role)
    if status is not None:
        statement = statement.where(User.status.is_(status))
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                User.username.ilike(pattern),
                User.real_name.ilike(pattern),
                User.student_no.ilike(pattern),
                User.teacher_no.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
    users = db.session.scalars(statement.order_by(User.created_at.desc(), User.id.desc())).all()
    return [item.to_dict() for item in users]


def change_user_status(user_id: int, status: bool) -> dict:
    user = db.session.get(User, user_id)
    if user is None:
        raise AdminNotFound("用户不存在")
    if user.role == UserRole.ADMIN.value:
        raise AdminConflict("管理员账号不能在此处禁用")
    if bool(user.status) == status:
        return user.to_dict()
    user.status = status
    db.session.commit()
    return user.to_dict()
