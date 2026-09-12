from flask_jwt_extended import create_access_token, create_refresh_token
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.constants import UserRole
from app.datetime_utils import utc_now
from app.extensions import db
from app.models import User
from app.services.password_reset_service import (
    PasswordResetRequestConflict,
    cancel_pending_password_resets,
    submit_student_password_reset,
)


class AuthenticationError(ValueError):
    pass


class ConflictError(ValueError):
    pass


def create_student(data: dict) -> User:
    return create_user(data, UserRole.STUDENT.value)


def create_user(data: dict, role: str) -> User:
    unique_values = [User.username == data["username"]]
    labels = {"username": "用户名"}
    for field in ("email", "student_no", "teacher_no"):
        value = data.get(field)
        if value:
            unique_values.append(getattr(User, field) == value)
            labels[field] = {"email": "邮箱", "student_no": "学号", "teacher_no": "工号"}[field]

    existing = db.session.scalar(db.select(User).where(or_(*unique_values)))
    if existing:
        for field, label in labels.items():
            value = data.get(field)
            if value and getattr(existing, field) == value:
                raise ConflictError(f"{label}已存在")
        raise ConflictError("账号信息已存在")

    user = User(
        username=data["username"],
        password_hash=generate_password_hash(data["password"]),
        real_name=data["real_name"],
        student_no=data.get("student_no"),
        teacher_no=data.get("teacher_no"),
        email=data.get("email"),
        phone=data.get("phone"),
        role=role,
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ConflictError("账号信息已存在") from exc
    return user


def authenticate(account: str, password: str) -> User:
    user = db.session.scalar(
        db.select(User).where(
            or_(User.username == account, User.email == account, User.student_no == account, User.teacher_no == account)
        )
    )
    if user is None or not check_password_hash(user.password_hash, password):
        raise AuthenticationError("账号或密码错误")
    if not user.status:
        raise AuthenticationError("账号已被禁用")

    user.last_login_at = utc_now()
    db.session.commit()
    return user


def issue_token_pair(user: User) -> dict:
    identity = str(user.id)
    claims = {"role": user.role}
    return {
        "access_token": create_access_token(identity=identity, additional_claims=claims),
        "refresh_token": create_refresh_token(identity=identity, additional_claims=claims),
        "user": user.to_dict(),
    }


def get_active_user(user_id: str | int) -> User:
    user = db.session.get(User, int(user_id))
    if user is None or not user.status:
        raise AuthenticationError("用户不存在或已禁用")
    return user


def reset_password(username: str, verification: str, new_password: str) -> str:
    user = db.session.scalar(db.select(User).where(User.username == username))
    values = {value for value in (user.email, user.student_no, user.teacher_no, user.phone) if value} if user else set()
    if user is None or verification not in values:
        raise AuthenticationError("账号信息核验失败，请检查用户名和验证信息")
    if user.role == UserRole.ADMIN.value:
        raise AuthenticationError("管理员账号不能通过公开入口重置密码")
    if not user.status:
        raise AuthenticationError("账号已被禁用，请联系管理员")
    if check_password_hash(user.password_hash, new_password):
        raise ConflictError("新密码不能与当前密码相同")
    if user.role == UserRole.STUDENT.value:
        try:
            submit_student_password_reset(user, new_password)
        except PasswordResetRequestConflict as exc:
            raise ConflictError(str(exc)) from exc
        return "PENDING"
    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return "COMPLETED"


def set_user_password(user_id: int, new_password: str, reviewer_id: int | None = None) -> User:
    user = db.session.get(User, user_id)
    if user is None:
        raise AuthenticationError("用户不存在")
    if check_password_hash(user.password_hash, new_password):
        raise ConflictError("新密码不能与当前密码相同")
    user.password_hash = generate_password_hash(new_password)
    cancel_pending_password_resets(user.id, reviewer_id)
    db.session.commit()
    return user
