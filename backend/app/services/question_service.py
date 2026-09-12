from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.constants import QuestionStatus, UserRole
from app.datetime_utils import iso_utc
from app.extensions import db
from app.models import Answer, Chapter, Course, Question, User, Video
from .learning_service import get_student_video
from .notification_service import queue_notification


class QuestionNotFound(ValueError):
    pass


class QuestionPermissionDenied(PermissionError):
    pass


class QuestionConflict(ValueError):
    pass


def create_question(student_id: int, data: dict) -> dict:
    video = get_student_video(student_id, data["video_id"])
    duration = float(video.duration or 0)
    if duration > 0 and data["video_time"] > duration + 1:
        raise ValueError("提问时间点不能超过视频时长")
    question = Question(
        student_id=student_id,
        video_id=video.id,
        video_time=min(data["video_time"], duration) if duration > 0 else data["video_time"],
        title=data["title"],
        content=data["content"],
        status=QuestionStatus.WAITING.value,
    )
    db.session.add(question)
    db.session.commit()
    return serialize_question(_get_question(question.id))


def list_questions(user_id: int, role: str, status: str | None = None, video_id: int | None = None) -> list[dict]:
    statement = _question_query()
    if role == UserRole.STUDENT.value:
        statement = statement.where(Question.student_id == user_id)
    elif role == UserRole.TEACHER.value:
        statement = (
            statement.join(Video, Video.id == Question.video_id)
            .join(Chapter, Chapter.id == Video.chapter_id)
            .join(Course, Course.id == Chapter.course_id)
            .where(Course.teacher_id == user_id)
        )
    else:
        raise QuestionPermissionDenied("无权查看答疑列表")
    if status is not None:
        statement = statement.where(Question.status == status)
    if video_id is not None:
        statement = statement.where(Question.video_id == video_id)
    questions = db.session.scalars(
        statement.order_by(Question.created_at.desc(), Question.id.desc())
    ).unique().all()
    return [serialize_question(question) for question in questions]


def get_visible_question(question_id: int, user_id: int, role: str) -> dict:
    question = _get_question(question_id)
    _ensure_question_access(question, user_id, role)
    return serialize_question(question)


def answer_question(question_id: int, teacher_id: int, content: str) -> dict:
    question = _get_question(question_id)
    _ensure_teacher_owns_question(question, teacher_id)
    if question.status == QuestionStatus.CLOSED.value:
        raise QuestionConflict("问题已关闭，不能回答")
    if question.answer is not None:
        raise QuestionConflict("该问题已经回答")
    answer = Answer(question_id=question.id, teacher_id=teacher_id, content=content)
    question.status = QuestionStatus.ANSWERED.value
    db.session.add(answer)
    queue_notification(
        question.student_id,
        f"问题已回复：{question.title}",
        "教师已经回复了你的课程问题，点击查看回复内容。",
        category="QUESTION",
        sender_id=teacher_id,
        link=f"/courses/{question.video.chapter.course_id}",
    )
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise QuestionConflict("该问题已经回答") from exc
    return serialize_question(_get_question(question.id))


def update_answer(question_id: int, teacher_id: int, content: str) -> dict:
    question = _get_question(question_id)
    _ensure_teacher_owns_question(question, teacher_id)
    if question.status == QuestionStatus.CLOSED.value:
        raise QuestionConflict("问题已关闭，不能修改回答")
    if question.answer is None:
        raise QuestionNotFound("回答不存在")
    if question.answer.teacher_id != teacher_id:
        raise QuestionPermissionDenied("不能修改其他教师的回答")
    question.answer.content = content
    queue_notification(
        question.student_id,
        f"课程答疑已更新：{question.title}",
        "教师更新了对你问题的回答，点击查看最新内容。",
        category="QUESTION",
        link=f"/courses/{question.video.chapter.course_id}",
        sender_id=teacher_id,
    )
    db.session.commit()
    return serialize_question(_get_question(question.id))


def close_question(question_id: int, user_id: int, role: str) -> dict:
    question = _get_question(question_id)
    _ensure_question_access(question, user_id, role)
    if question.status == QuestionStatus.CLOSED.value:
        raise QuestionConflict("问题已经关闭")
    question.status = QuestionStatus.CLOSED.value
    db.session.commit()
    return serialize_question(question)


def serialize_question(question: Question) -> dict:
    video = question.video
    course = video.chapter.course if video and video.chapter else None
    answer = question.answer
    return {
        "id": question.id,
        "student_id": question.student_id,
        "student_name": question.student.real_name if question.student else None,
        "video_id": question.video_id,
        "video_title": video.title if video else None,
        "course_id": course.id if course else None,
        "course_name": course.name if course else None,
        "video_time": float(question.video_time or 0),
        "title": question.title,
        "content": question.content,
        "status": question.status,
        "created_at": iso_utc(question.created_at),
        "updated_at": iso_utc(question.updated_at),
        "answer": (
            {
                "id": answer.id,
                "teacher_id": answer.teacher_id,
                "teacher_name": answer.teacher.real_name if answer.teacher else None,
                "content": answer.content,
                "created_at": iso_utc(answer.created_at),
                "updated_at": iso_utc(answer.updated_at),
            }
            if answer
            else None
        ),
    }


def _question_query():
    return db.select(Question).options(
        joinedload(Question.student),
        joinedload(Question.video)
        .joinedload(Video.chapter)
        .joinedload(Chapter.course)
        .joinedload(Course.teacher),
        selectinload(Question.answer).joinedload(Answer.teacher),
    )


def _get_question(question_id: int) -> Question:
    question = db.session.scalar(_question_query().where(Question.id == question_id))
    if question is None:
        raise QuestionNotFound("问题不存在")
    return question


def _ensure_question_access(question: Question, user_id: int, role: str) -> None:
    if role == UserRole.STUDENT.value and question.student_id == user_id:
        return
    if role == UserRole.TEACHER.value:
        _ensure_teacher_owns_question(question, user_id)
        return
    raise QuestionPermissionDenied("无权查看该问题")


def _ensure_teacher_owns_question(question: Question, teacher_id: int) -> None:
    course = question.video.chapter.course
    if course.teacher_id != teacher_id:
        raise QuestionPermissionDenied("不能处理其他教师课程的问题")
