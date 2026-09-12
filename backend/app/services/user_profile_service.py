from pathlib import Path

from flask import current_app
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.constants import CourseStatus, UserRole
from app.datetime_utils import iso_utc
from app.extensions import db
from app.models import Course, User
from app.services.file_service import remove_media_file, save_profile_avatar


class ProfileNotFound(ValueError):
    pass


class ProfileConflict(ValueError):
    pass


def get_public_profile(user_id: int) -> dict:
    user = db.session.get(User, user_id)
    if user is None or not user.status:
        raise ProfileNotFound("用户主页不存在")

    courses = []
    if user.role == UserRole.TEACHER.value:
        teacher_courses = db.session.scalars(
            db.select(Course)
            .options(selectinload(Course.category))
            .where(
                Course.teacher_id == user.id,
                Course.status == CourseStatus.PUBLISHED.value,
            )
            .order_by(Course.published_at.desc(), Course.id.desc())
        ).all()
        courses = [
            {
                "id": course.id,
                "name": course.name,
                "description": course.description,
                "category_name": course.category.name if course.category else None,
                "cover_url": f"/media/{course.cover}" if course.cover else None,
            }
            for course in teacher_courses
        ]

    return {
        "id": user.id,
        "real_name": user.real_name,
        "role": user.role,
        "teacher_no": user.teacher_no if user.role == UserRole.TEACHER.value else None,
        "avatar_url": f"/media/{user.avatar}" if user.avatar else None,
        "bio": user.bio,
        "created_at": iso_utc(user.created_at),
        "courses": courses,
    }


def update_profile(user_id: int, data: dict) -> dict:
    user = _active_user(user_id)
    email = data.get("email")
    if email:
        existing = db.session.scalar(
            db.select(User.id).where(User.email == email, User.id != user.id)
        )
        if existing is not None:
            raise ProfileConflict("该邮箱已被其他账号使用")
    for field, value in data.items():
        setattr(user, field, value)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ProfileConflict("该邮箱已被其他账号使用") from exc
    return user.to_dict()


def update_avatar(user_id: int, file) -> dict:
    user = _active_user(user_id)
    media_root = Path(current_app.config["MEDIA_ROOT"])
    new_path = save_profile_avatar(
        file,
        media_root / "avatars",
        int(current_app.config["AVATAR_MAX_LENGTH"]),
    )
    relative_path = new_path.relative_to(media_root).as_posix()
    old_path = user.avatar
    try:
        user.avatar = relative_path
        db.session.commit()
    except Exception:
        db.session.rollback()
        _discard_avatar_file(media_root, relative_path)
        raise
    if old_path and old_path != relative_path:
        _discard_avatar_file(media_root, old_path)
    return user.to_dict()


def delete_avatar(user_id: int) -> dict:
    user = _active_user(user_id)
    old_path = user.avatar
    user.avatar = None
    db.session.commit()
    if old_path:
        _discard_avatar_file(Path(current_app.config["MEDIA_ROOT"]), old_path)
    return user.to_dict()


def _active_user(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None or not user.status:
        raise ProfileNotFound("用户不存在或已禁用")
    return user


def _discard_avatar_file(media_root: Path, relative_path: str) -> None:
    try:
        remove_media_file(media_root, relative_path)
    except (OSError, ValueError):
        current_app.logger.warning("头像文件清理失败：%s", relative_path, exc_info=True)
