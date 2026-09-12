import shutil
import subprocess
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from flask import current_app
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.constants import CourseStatus, UserRole, VideoStatus
from app.datetime_utils import iso_utc, utc_now
from app.extensions import db
from app.models import (
    Chapter,
    Course,
    CourseCategory,
    TeachingClass,
    TeachingClassStudent,
    User,
    Video,
)
from .file_service import clear_generated_video_files, remove_all_video_files


class AdminNotFound(ValueError):
    pass


class AdminConflict(ValueError):
    pass


VIDEO_STALE_AFTER = timedelta(minutes=30)


def list_users(
    page: int,
    page_size: int,
    role: str | None = None,
    status: bool | None = None,
    keyword: str | None = None,
) -> dict:
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
    pagination = db.paginate(
        statement.order_by(User.created_at.desc(), User.id.desc()),
        page=page,
        per_page=page_size,
        error_out=False,
    )
    return {
        "items": [item.to_dict() for item in pagination.items],
        "pagination": _pagination_payload(pagination),
    }


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


def list_video_operations(
    page: int,
    page_size: int,
    status: str | None = None,
    keyword: str | None = None,
) -> dict:
    statement = db.select(Video).options(
        joinedload(Video.chapter)
        .joinedload(Chapter.course)
        .joinedload(Course.teacher)
    )
    if status:
        statement = statement.where(Video.status == status)
    if keyword:
        pattern = f"%{keyword}%"
        statement = (
            statement.join(Chapter, Video.chapter_id == Chapter.id)
            .join(Course, Chapter.course_id == Course.id)
            .join(User, Course.teacher_id == User.id)
            .where(
                or_(
                    Video.title.ilike(pattern),
                    Video.original_name.ilike(pattern),
                    Course.name.ilike(pattern),
                    User.real_name.ilike(pattern),
                    User.teacher_no.ilike(pattern),
                )
            )
        )
    pagination = db.paginate(
        statement.order_by(Video.updated_at.desc(), Video.id.desc()),
        page=page,
        per_page=page_size,
        error_out=False,
    )
    counts = {item.value: 0 for item in VideoStatus}
    for current_status, count in db.session.execute(
        db.select(Video.status, func.count(Video.id)).group_by(Video.status)
    ).all():
        counts[current_status] = int(count)
    return {
        "items": [serialize_admin_video(video) for video in pagination.items],
        "pagination": _pagination_payload(pagination),
        "summary": {"total": sum(counts.values()), **counts},
        "runtime": video_runtime_status(),
    }


def get_admin_video(video_id: int) -> Video:
    video = db.session.scalar(
        db.select(Video)
        .options(
            joinedload(Video.chapter)
            .joinedload(Chapter.course)
            .joinedload(Course.teacher)
        )
        .where(Video.id == video_id)
    )
    if video is None:
        raise AdminNotFound("视频不存在")
    return video


def prepare_video_retry(video_id: int) -> Video:
    video = get_admin_video(video_id)
    if not _video_retryable(video):
        if video.status in {VideoStatus.PENDING.value, VideoStatus.PROCESSING.value}:
            raise AdminConflict("视频任务仍在正常处理窗口内，请稍后再试")
        raise AdminConflict("只有失败或超过30分钟未更新的任务可以重新转码")
    original_path = _video_original_path(video)
    if original_path is None or not original_path.is_file():
        raise AdminConflict("原始视频文件已丢失，无法重新转码")
    clear_generated_video_files(Path(current_app.config["MEDIA_ROOT"]), video.id)
    video.status = VideoStatus.PENDING.value
    video.process_step = "QUEUED"
    video.error_message = None
    video.processed_file = None
    video.hls_path = None
    video.cover = None
    db.session.commit()
    return video


def delete_failed_video(video_id: int) -> None:
    video = get_admin_video(video_id)
    if video.status != VideoStatus.FAILED.value:
        raise AdminConflict("只有失败的视频任务可以清理")
    original_file = video.original_file
    db.session.delete(video)
    db.session.commit()
    try:
        remove_all_video_files(
            Path(current_app.config["MEDIA_ROOT"]),
            video_id,
            original_file,
        )
    except (OSError, ValueError):
        current_app.logger.exception("管理员清理视频 %s 的媒体文件失败", video_id)


def serialize_admin_video(video: Video) -> dict:
    course = video.chapter.course
    original_path = _video_original_path(video)
    original_exists = bool(original_path and original_path.is_file())
    return {
        **video.to_dict(),
        "course_id": course.id,
        "course_name": course.name,
        "course_status": course.status,
        "chapter_title": video.chapter.title,
        "teacher_id": course.teacher_id,
        "teacher_name": course.teacher.real_name,
        "teacher_no": course.teacher.teacher_no,
        "created_at": iso_utc(video.created_at),
        "updated_at": iso_utc(video.updated_at),
        "original_exists": original_exists,
        "retryable": original_exists and _video_retryable(video),
        "removable": video.status == VideoStatus.FAILED.value,
    }


def video_runtime_status() -> dict:
    return {
        "mode": "ASYNC" if current_app.config["VIDEO_PROCESSING_ASYNC"] else "SYNC",
        "ffmpeg": _binary_status(current_app.config["FFMPEG_BIN"]),
        "ffprobe": _binary_status(current_app.config["FFPROBE_BIN"]),
        "stale_after_minutes": int(VIDEO_STALE_AFTER.total_seconds() // 60),
    }


def list_admin_courses(
    page: int,
    page_size: int,
    status: str | None = None,
    keyword: str | None = None,
) -> dict:
    statement = db.select(Course).options(
        selectinload(Course.teacher),
        selectinload(Course.category),
        selectinload(Course.chapters).selectinload(Chapter.videos),
        selectinload(Course.student_links),
    )
    if status:
        statement = statement.where(Course.status == status)
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.join(User, Course.teacher_id == User.id).where(
            or_(
                Course.name.ilike(pattern),
                User.real_name.ilike(pattern),
                User.teacher_no.ilike(pattern),
            )
        )
    pagination = db.paginate(
        statement.order_by(Course.updated_at.desc(), Course.id.desc()),
        page=page,
        per_page=page_size,
        error_out=False,
    )
    return {
        "items": [serialize_admin_course(course) for course in pagination.items],
        "pagination": _pagination_payload(pagination),
    }


def serialize_admin_course(course: Course) -> dict:
    return {
        "id": course.id,
        "name": course.name,
        "status": course.status,
        "teacher_id": course.teacher_id,
        "teacher_name": course.teacher.real_name,
        "teacher_no": course.teacher.teacher_no,
        "category_name": course.category.name,
        "chapter_count": len(course.chapters),
        "video_count": sum(len(chapter.videos) for chapter in course.chapters),
        "ready_video_count": sum(
            video.status == VideoStatus.READY.value
            for chapter in course.chapters
            for video in chapter.videos
        ),
        "student_count": sum(link.status for link in course.student_links),
        "published_at": iso_utc(course.published_at),
        "updated_at": iso_utc(course.updated_at),
    }


def _get_admin_course(course_id: int) -> Course:
    course = db.session.scalar(
        db.select(Course)
        .options(
            selectinload(Course.teacher),
            selectinload(Course.category),
            selectinload(Course.chapters).selectinload(Chapter.videos),
            selectinload(Course.student_links),
        )
        .where(Course.id == course_id)
    )
    if course is None:
        raise AdminNotFound("课程不存在")
    return course


def change_admin_course_status(course_id: int, status: CourseStatus) -> dict:
    course = db.session.get(Course, course_id)
    if course is None:
        raise AdminNotFound("课程不存在")
    if course.status == status.value:
        return serialize_admin_course(_get_admin_course(course.id))
    if status is CourseStatus.OFFLINE:
        if course.status != CourseStatus.PUBLISHED.value:
            raise AdminConflict("只有已发布课程可以强制下线")
    elif status is CourseStatus.PUBLISHED:
        if course.status not in {CourseStatus.DRAFT.value, CourseStatus.OFFLINE.value}:
            raise AdminConflict("当前课程状态不能发布")
        chapter_count = db.session.scalar(
            db.select(func.count(Chapter.id)).where(Chapter.course_id == course.id)
        )
        if not chapter_count:
            raise AdminConflict("课程至少包含一个章节后才能发布")
        course.published_at = utc_now()
    else:
        raise AdminConflict("管理员只能发布或下线课程")
    course.status = status.value
    db.session.commit()
    return serialize_admin_course(_get_admin_course(course.id))


def list_admin_classes(keyword: str | None = None) -> list[dict]:
    statement = db.select(TeachingClass).options(
        selectinload(TeachingClass.teacher),
        selectinload(TeachingClass.student_links),
    )
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.join(User, TeachingClass.teacher_id == User.id).where(
            or_(
                TeachingClass.name.ilike(pattern),
                TeachingClass.description.ilike(pattern),
                User.real_name.ilike(pattern),
                User.teacher_no.ilike(pattern),
            )
        )
    classrooms = db.session.scalars(
        statement.order_by(TeachingClass.updated_at.desc(), TeachingClass.id.desc())
    ).unique().all()
    return [
        {
            "id": classroom.id,
            "name": classroom.name,
            "description": classroom.description,
            "teacher_id": classroom.teacher_id,
            "teacher_name": classroom.teacher.real_name,
            "teacher_no": classroom.teacher.teacher_no,
            "member_count": len(classroom.student_links),
            "created_at": iso_utc(classroom.created_at),
            "updated_at": iso_utc(classroom.updated_at),
        }
        for classroom in classrooms
    ]


def delete_admin_class(class_id: int) -> str:
    classroom = db.session.get(TeachingClass, class_id)
    if classroom is None:
        raise AdminNotFound("班级不存在")
    name = classroom.name
    db.session.delete(classroom)
    db.session.commit()
    return name


def list_admin_categories() -> list[dict]:
    categories = db.session.scalars(
        db.select(CourseCategory)
        .options(selectinload(CourseCategory.courses))
        .order_by(CourseCategory.sort_order, CourseCategory.id)
    ).all()
    return [serialize_admin_category(category) for category in categories]


def create_admin_category(data: dict) -> dict:
    category = CourseCategory(**data)
    db.session.add(category)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise AdminConflict("课程分类名称已存在") from exc
    return serialize_admin_category(category)


def update_admin_category(category_id: int, data: dict) -> dict:
    category = db.session.get(CourseCategory, category_id)
    if category is None:
        raise AdminNotFound("课程分类不存在")
    for field, value in data.items():
        setattr(category, field, value)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise AdminConflict("课程分类名称已存在") from exc
    return serialize_admin_category(category)


def change_admin_category_status(category_id: int, status: bool) -> dict:
    category = db.session.get(CourseCategory, category_id)
    if category is None:
        raise AdminNotFound("课程分类不存在")
    category.status = status
    db.session.commit()
    return serialize_admin_category(category)


def serialize_admin_category(category: CourseCategory) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "sort_order": category.sort_order,
        "status": bool(category.status),
        "course_count": len(category.courses),
        "created_at": iso_utc(category.created_at),
        "updated_at": iso_utc(category.updated_at),
    }


def _video_retryable(video: Video) -> bool:
    if video.status == VideoStatus.FAILED.value:
        return True
    if video.status not in {VideoStatus.PENDING.value, VideoStatus.PROCESSING.value}:
        return False
    return bool(video.updated_at and video.updated_at <= utc_now() - VIDEO_STALE_AFTER)


def _video_original_path(video: Video) -> Path | None:
    if not video.original_file:
        return None
    media_root = Path(current_app.config["MEDIA_ROOT"]).resolve()
    original_path = (media_root / video.original_file).resolve()
    if original_path == media_root or not original_path.is_relative_to(media_root):
        return None
    return original_path


@lru_cache(maxsize=8)
def _binary_status(command: str) -> dict:
    path = Path(command)
    resolved = str(path) if path.is_file() else shutil.which(command)
    result = {
        "available": bool(resolved),
        "command": Path(resolved or command).name,
        "version": None,
    }
    if not resolved:
        return result
    try:
        process = subprocess.run(
            [resolved, "-version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
        first_line = (process.stdout or process.stderr or "").splitlines()
        result["available"] = process.returncode == 0
        result["version"] = first_line[0][:160] if first_line else None
    except (OSError, subprocess.TimeoutExpired):
        result["available"] = False
    return result


def _pagination_payload(pagination) -> dict:
    return {
        "page": pagination.page,
        "page_size": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
    }
