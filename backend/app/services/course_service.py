from datetime import datetime, timezone
from pathlib import Path

from flask import current_app
from sqlalchemy.orm import selectinload

from app.constants import CourseStatus, VideoStatus
from app.extensions import db
from app.models import Chapter, Course, CourseCategory, Video
from .file_service import remove_all_video_files


class CourseNotFound(ValueError):
    pass


class CoursePermissionDenied(PermissionError):
    pass


class CourseStateError(ValueError):
    pass


def list_categories() -> list[dict]:
    categories = db.session.scalars(
        db.select(CourseCategory)
        .where(CourseCategory.status.is_(True))
        .order_by(CourseCategory.sort_order, CourseCategory.id)
    ).all()
    return [{"id": item.id, "name": item.name, "description": item.description} for item in categories]


def list_published_courses(category_id: int | None = None) -> list[dict]:
    statement = (
        db.select(Course)
        .options(selectinload(Course.category), selectinload(Course.teacher))
        .where(Course.status == CourseStatus.PUBLISHED.value)
        .order_by(Course.published_at.desc(), Course.id.desc())
    )
    if category_id is not None:
        statement = statement.where(Course.category_id == category_id)
    return [serialize_course(course) for course in db.session.scalars(statement).all()]


def list_teacher_courses(teacher_id: int) -> list[dict]:
    statement = (
        db.select(Course)
        .options(
            selectinload(Course.category),
            selectinload(Course.teacher),
            selectinload(Course.chapters).selectinload(Chapter.videos),
        )
        .where(Course.teacher_id == teacher_id)
        .order_by(Course.created_at.desc())
    )
    return [serialize_course(course, include_chapters=True) for course in db.session.scalars(statement).all()]


def get_visible_course(course_id: int, viewer_id: int | None = None, viewer_role: str | None = None) -> dict:
    course = _get_course(course_id, with_chapters=True)
    can_manage = viewer_role == "ADMIN" or (viewer_role == "TEACHER" and course.teacher_id == viewer_id)
    if course.status != CourseStatus.PUBLISHED.value and not can_manage:
        raise CourseNotFound("课程不存在")
    return serialize_course(course, include_chapters=True, include_unready_videos=can_manage)


def create_course(teacher_id: int, data: dict) -> dict:
    _ensure_active_category(data["category_id"])
    course = Course(teacher_id=teacher_id, **data)
    db.session.add(course)
    db.session.commit()
    return serialize_course(_get_course(course.id))


def update_course(course_id: int, teacher_id: int, data: dict) -> dict:
    course = _owned_course(course_id, teacher_id)
    if course.status != CourseStatus.DRAFT.value:
        raise CourseStateError("只有草稿课程可以编辑")
    if "category_id" in data:
        _ensure_active_category(data["category_id"])
    for field, value in data.items():
        setattr(course, field, value)
    db.session.commit()
    return serialize_course(_get_course(course.id))


def change_course_status(course_id: int, teacher_id: int, status: CourseStatus) -> dict:
    course = _owned_course(course_id, teacher_id)
    if status is CourseStatus.PUBLISHED:
        chapter_count = db.session.scalar(
            db.select(db.func.count()).select_from(Chapter).where(Chapter.course_id == course.id)
        )
        if not chapter_count:
            raise CourseStateError("课程至少包含一个章节后才能发布")
        course.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
    course.status = status.value
    db.session.commit()
    return serialize_course(_get_course(course.id))


def delete_draft_course(course_id: int, teacher_id: int) -> None:
    course = _owned_course(course_id, teacher_id)
    if course.status != CourseStatus.DRAFT.value:
        raise CourseStateError("只有草稿课程可以删除，已发布课程请下线")
    video_files = db.session.execute(
        db.select(Video.id, Video.original_file)
        .join(Chapter, Video.chapter_id == Chapter.id)
        .where(Chapter.course_id == course.id)
    ).all()
    db.session.delete(course)
    db.session.commit()
    _cleanup_deleted_video_files(video_files)


def create_chapter(course_id: int, teacher_id: int, data: dict) -> dict:
    course = _owned_course(course_id, teacher_id)
    if course.status != CourseStatus.DRAFT.value:
        raise CourseStateError("只有草稿课程可以新增章节")
    chapter = Chapter(course_id=course.id, **data)
    db.session.add(chapter)
    db.session.commit()
    return serialize_chapter(chapter)


def update_chapter(course_id: int, chapter_id: int, teacher_id: int, data: dict) -> dict:
    course = _owned_course(course_id, teacher_id)
    if course.status != CourseStatus.DRAFT.value:
        raise CourseStateError("只有草稿课程可以编辑章节")
    chapter = db.session.scalar(
        db.select(Chapter).where(Chapter.id == chapter_id, Chapter.course_id == course.id)
    )
    if chapter is None:
        raise CourseNotFound("章节不存在")
    for field, value in data.items():
        setattr(chapter, field, value)
    db.session.commit()
    return serialize_chapter(chapter)


def delete_chapter(course_id: int, chapter_id: int, teacher_id: int) -> None:
    course = _owned_course(course_id, teacher_id)
    if course.status != CourseStatus.DRAFT.value:
        raise CourseStateError("只有草稿课程可以删除章节")
    chapter = db.session.scalar(
        db.select(Chapter).where(Chapter.id == chapter_id, Chapter.course_id == course.id)
    )
    if chapter is None:
        raise CourseNotFound("章节不存在")
    video_files = db.session.execute(
        db.select(Video.id, Video.original_file).where(Video.chapter_id == chapter.id)
    ).all()
    db.session.delete(chapter)
    db.session.commit()
    _cleanup_deleted_video_files(video_files)


def serialize_course(
    course: Course,
    include_chapters: bool = False,
    include_unready_videos: bool = True,
) -> dict:
    payload = {
        "id": course.id,
        "teacher_id": course.teacher_id,
        "teacher_name": course.teacher.real_name if course.teacher else None,
        "category_id": course.category_id,
        "category_name": course.category.name if course.category else None,
        "name": course.name,
        "cover": course.cover,
        "description": course.description,
        "detail": course.detail,
        "status": course.status,
        "published_at": course.published_at.isoformat() if course.published_at else None,
        "created_at": course.created_at.isoformat() if course.created_at else None,
        "updated_at": course.updated_at.isoformat() if course.updated_at else None,
    }
    if include_chapters:
        payload["chapters"] = [
            serialize_chapter(chapter, include_unready_videos=include_unready_videos)
            for chapter in sorted(course.chapters, key=lambda item: (item.sort_order, item.id))
        ]
    return payload


def serialize_chapter(chapter: Chapter, include_unready_videos: bool = True) -> dict:
    videos = sorted(chapter.videos, key=lambda item: (item.sort_order, item.id))
    if not include_unready_videos:
        videos = [video for video in videos if video.status == VideoStatus.READY.value]
    return {
        "id": chapter.id,
        "course_id": chapter.course_id,
        "title": chapter.title,
        "description": chapter.description,
        "sort_order": chapter.sort_order,
        "videos": [video.to_dict() for video in videos],
    }


def _get_course(course_id: int, with_chapters: bool = False) -> Course:
    options = [selectinload(Course.category), selectinload(Course.teacher)]
    if with_chapters:
        options.append(selectinload(Course.chapters).selectinload(Chapter.videos))
    course = db.session.scalar(db.select(Course).options(*options).where(Course.id == course_id))
    if course is None:
        raise CourseNotFound("课程不存在")
    return course


def _owned_course(course_id: int, teacher_id: int) -> Course:
    course = _get_course(course_id)
    if course.teacher_id != teacher_id:
        raise CoursePermissionDenied("不能操作其他教师的课程")
    return course


def _ensure_active_category(category_id: int) -> None:
    category = db.session.get(CourseCategory, category_id)
    if category is None or not category.status:
        raise CourseNotFound("课程分类不存在或已禁用")


def _cleanup_deleted_video_files(video_files) -> None:
    media_root = Path(current_app.config["MEDIA_ROOT"])
    for video_id, original_file in video_files:
        try:
            remove_all_video_files(media_root, video_id, original_file)
        except (OSError, ValueError):
            current_app.logger.exception("视频 %s 的媒体文件清理失败", video_id)
