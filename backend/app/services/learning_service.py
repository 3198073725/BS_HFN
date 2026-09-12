from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.constants import CourseStatus, LearningStatus, VideoStatus
from app.datetime_utils import iso_utc, utc_now
from app.extensions import db
from app.models import Chapter, Course, CourseStudent, Favorite, LearningRecord, Video, VideoNote
from .course_service import serialize_course


class LearningNotFound(ValueError):
    pass


class LearningPermissionDenied(PermissionError):
    pass


class LearningConflict(ValueError):
    pass


def join_course(student_id: int, course_id: int) -> dict:
    course = _published_course(course_id)
    link = db.session.scalar(
        db.select(CourseStudent).where(
            CourseStudent.course_id == course.id,
            CourseStudent.student_id == student_id,
        )
    )
    if link is not None and link.status:
        raise LearningConflict("已经加入该课程")
    if link is None:
        link = CourseStudent(course_id=course.id, student_id=student_id)
        db.session.add(link)
    else:
        link.status = True
        link.join_time = _now()
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise LearningConflict("已经加入该课程") from exc
    return serialize_course_state(student_id, course.id)


def leave_course(student_id: int, course_id: int) -> None:
    link = db.session.scalar(
        db.select(CourseStudent).where(
            CourseStudent.course_id == course_id,
            CourseStudent.student_id == student_id,
            CourseStudent.status.is_(True),
        )
    )
    if link is None:
        raise LearningNotFound("尚未加入该课程")
    link.status = False
    db.session.commit()


def add_favorite(student_id: int, course_id: int) -> dict:
    _published_course(course_id)
    existing = db.session.scalar(
        db.select(Favorite).where(Favorite.student_id == student_id, Favorite.course_id == course_id)
    )
    if existing is not None:
        raise LearningConflict("已经收藏该课程")
    favorite = Favorite(student_id=student_id, course_id=course_id)
    db.session.add(favorite)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise LearningConflict("已经收藏该课程") from exc
    return serialize_favorite(favorite)


def remove_favorite(student_id: int, course_id: int) -> None:
    favorite = db.session.scalar(
        db.select(Favorite).where(Favorite.student_id == student_id, Favorite.course_id == course_id)
    )
    if favorite is None:
        raise LearningNotFound("尚未收藏该课程")
    db.session.delete(favorite)
    db.session.commit()


def serialize_course_state(student_id: int, course_id: int) -> dict:
    _published_course(course_id)
    joined = db.session.scalar(
        db.select(CourseStudent.id).where(
            CourseStudent.course_id == course_id,
            CourseStudent.student_id == student_id,
            CourseStudent.status.is_(True),
        )
    )
    favorited = db.session.scalar(
        db.select(Favorite.id).where(Favorite.course_id == course_id, Favorite.student_id == student_id)
    )
    return {"course_id": course_id, "joined": joined is not None, "favorited": favorited is not None}


def list_joined_courses(student_id: int) -> list[dict]:
    links = db.session.scalars(
        db.select(CourseStudent)
        .options(
            joinedload(CourseStudent.course).joinedload(Course.category),
            joinedload(CourseStudent.course).joinedload(Course.teacher),
        )
        .join(Course, Course.id == CourseStudent.course_id)
        .where(
            CourseStudent.student_id == student_id,
            CourseStudent.status.is_(True),
            Course.status == CourseStatus.PUBLISHED.value,
        )
        .order_by(CourseStudent.join_time.desc(), CourseStudent.id.desc())
    ).unique().all()
    progress_by_course = _course_progress(student_id)
    result = []
    for link in links:
        item = serialize_course(link.course)
        item["join_time"] = iso_utc(link.join_time)
        item["learning_progress"] = progress_by_course.get(link.course_id, 0.0)
        result.append(item)
    return result


def list_favorites(student_id: int) -> list[dict]:
    favorites = db.session.scalars(
        db.select(Favorite)
        .options(
            joinedload(Favorite.course).joinedload(Course.category),
            joinedload(Favorite.course).joinedload(Course.teacher),
        )
        .join(Course, Course.id == Favorite.course_id)
        .where(Favorite.student_id == student_id, Course.status == CourseStatus.PUBLISHED.value)
        .order_by(Favorite.created_at.desc(), Favorite.id.desc())
    ).unique().all()
    return [serialize_favorite(item) for item in favorites]


def get_progress(student_id: int, video_id: int) -> dict:
    get_student_video(student_id, video_id)
    record = db.session.scalar(
        db.select(LearningRecord).where(
            LearningRecord.student_id == student_id,
            LearningRecord.video_id == video_id,
        )
    )
    if record is None:
        return {
            "id": None,
            "student_id": student_id,
            "video_id": video_id,
            "current_time": 0.0,
            "watch_duration": 0,
            "progress": 0.0,
            "status": LearningStatus.NOT_STARTED.value,
            "last_watch_time": None,
        }
    return serialize_progress(record)


def update_progress(student_id: int, video_id: int, current_time: float, watch_delta: int) -> dict:
    video = get_student_video(student_id, video_id)
    normalized_time = _checked_video_time(video, current_time)
    record = db.session.scalar(
        db.select(LearningRecord).where(
            LearningRecord.student_id == student_id,
            LearningRecord.video_id == video_id,
        ).with_for_update()
    )
    if record is None:
        record = LearningRecord(student_id=student_id, video_id=video_id)
        db.session.add(record)

    duration = float(video.duration or 0)
    progress = min(normalized_time / duration * 100, 100) if duration > 0 else 0
    record.current_time = round(normalized_time, 3)
    record.watch_duration = int(record.watch_duration or 0) + watch_delta
    record.progress = round(progress, 2)
    record.status = (
        LearningStatus.COMPLETED.value if progress >= 90 else LearningStatus.LEARNING.value
    )
    record.last_watch_time = _now()
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise LearningConflict("学习进度更新冲突，请重试") from exc
    return serialize_progress(record)


def list_notes(student_id: int, video_id: int) -> list[dict]:
    get_student_video(student_id, video_id)
    notes = db.session.scalars(
        db.select(VideoNote)
        .where(VideoNote.student_id == student_id, VideoNote.video_id == video_id)
        .order_by(VideoNote.video_time, VideoNote.created_at, VideoNote.id)
    ).all()
    return [serialize_note(note) for note in notes]


def create_note(student_id: int, video_id: int, video_time: float, content: str) -> dict:
    video = get_student_video(student_id, video_id)
    note = VideoNote(
        student_id=student_id,
        video_id=video.id,
        video_time=_checked_video_time(video, video_time),
        content=content,
    )
    db.session.add(note)
    db.session.commit()
    return serialize_note(note)


def update_note(student_id: int, note_id: int, data: dict) -> dict:
    note = _owned_note(student_id, note_id)
    video = get_student_video(student_id, note.video_id)
    if "video_time" in data:
        note.video_time = _checked_video_time(video, data["video_time"])
    if "content" in data:
        note.content = data["content"]
    db.session.commit()
    return serialize_note(note)


def delete_note(student_id: int, note_id: int) -> None:
    note = _owned_note(student_id, note_id)
    get_student_video(student_id, note.video_id)
    db.session.delete(note)
    db.session.commit()


def get_student_video(student_id: int, video_id: int) -> Video:
    video = db.session.scalar(
        db.select(Video)
        .options(joinedload(Video.chapter).joinedload(Chapter.course))
        .where(Video.id == video_id)
    )
    if (
        video is None
        or video.status != VideoStatus.READY.value
        or video.chapter.course.status != CourseStatus.PUBLISHED.value
    ):
        raise LearningNotFound("视频不存在或暂不可学习")
    joined = db.session.scalar(
        db.select(CourseStudent.id).where(
            CourseStudent.course_id == video.chapter.course_id,
            CourseStudent.student_id == student_id,
            CourseStudent.status.is_(True),
        )
    )
    if joined is None:
        raise LearningPermissionDenied("请先加入课程")
    return video


def serialize_progress(record: LearningRecord) -> dict:
    return {
        "id": record.id,
        "student_id": record.student_id,
        "video_id": record.video_id,
        "current_time": float(record.current_time or 0),
        "watch_duration": int(record.watch_duration or 0),
        "progress": float(record.progress or 0),
        "status": record.status,
        "last_watch_time": iso_utc(record.last_watch_time),
    }


def serialize_note(note: VideoNote) -> dict:
    return {
        "id": note.id,
        "student_id": note.student_id,
        "video_id": note.video_id,
        "video_time": float(note.video_time or 0),
        "content": note.content,
        "created_at": iso_utc(note.created_at),
        "updated_at": iso_utc(note.updated_at),
    }


def serialize_favorite(favorite: Favorite) -> dict:
    payload = serialize_course(favorite.course) if favorite.course else {"id": favorite.course_id}
    payload["favorite_id"] = favorite.id
    payload["favorited_at"] = iso_utc(favorite.created_at)
    return payload


def _published_course(course_id: int) -> Course:
    course = db.session.scalar(
        db.select(Course)
        .options(joinedload(Course.category), joinedload(Course.teacher))
        .where(Course.id == course_id, Course.status == CourseStatus.PUBLISHED.value)
    )
    if course is None:
        raise LearningNotFound("课程不存在或尚未发布")
    return course


def _owned_note(student_id: int, note_id: int) -> VideoNote:
    note = db.session.get(VideoNote, note_id)
    if note is None:
        raise LearningNotFound("笔记不存在")
    if note.student_id != student_id:
        raise LearningPermissionDenied("不能操作其他学生的笔记")
    return note


def _checked_video_time(video: Video, value: float) -> float:
    duration = float(video.duration or 0)
    if value < 0:
        raise ValueError("视频时间不能小于0")
    if duration > 0 and value > duration + 1:
        raise ValueError("视频时间不能超过视频时长")
    return min(value, duration) if duration > 0 else value


def _course_progress(student_id: int) -> dict[int, float]:
    rows = db.session.execute(
        db.select(
            Chapter.course_id,
            db.func.coalesce(db.func.sum(LearningRecord.progress), 0)
            / db.func.nullif(db.func.count(Video.id), 0),
        )
        .join(Video, Video.chapter_id == Chapter.id)
        .outerjoin(
            LearningRecord,
            and_(
                LearningRecord.video_id == Video.id,
                LearningRecord.student_id == student_id,
            ),
        )
        .where(Video.status == VideoStatus.READY.value)
        .group_by(Chapter.course_id)
    ).all()
    return {course_id: round(float(progress or 0), 2) for course_id, progress in rows}


def _now():
    return utc_now()
