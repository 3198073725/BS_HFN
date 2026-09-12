from pathlib import Path

from flask import current_app
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.constants import CourseStatus, PublishStatus, UserRole
from app.datetime_utils import iso_utc, utc_now
from app.extensions import db
from app.models import Course, CourseStudent, Homework, HomeworkSubmission
from app.services.file_service import clear_homework_files, remove_media_file, save_homework_attachment
from app.services.notification_service import queue_course_notifications, queue_notification


class HomeworkNotFound(ValueError):
    pass


class HomeworkPermissionDenied(PermissionError):
    pass


class HomeworkConflict(ValueError):
    pass


def create_homework(teacher_id: int, data: dict) -> dict:
    course = _teacher_course(data["course_id"], teacher_id)
    if course.status == CourseStatus.OFFLINE.value:
        raise HomeworkConflict("下线课程不能创建作业")
    homework = Homework(teacher_id=teacher_id, **data)
    db.session.add(homework)
    db.session.commit()
    return serialize_homework(_get_homework(homework.id))


def update_homework(homework_id: int, teacher_id: int, data: dict) -> dict:
    homework = _teacher_homework(homework_id, teacher_id)
    if homework.status != PublishStatus.DRAFT.value:
        raise HomeworkConflict("只有草稿作业可以编辑")
    if "course_id" in data:
        course = _teacher_course(data["course_id"], teacher_id)
        if course.status == CourseStatus.OFFLINE.value:
            raise HomeworkConflict("下线课程不能设置作业")
    for field, value in data.items():
        setattr(homework, field, value)
    db.session.commit()
    return serialize_homework(_get_homework(homework.id))


def delete_draft_homework(homework_id: int, teacher_id: int) -> None:
    homework = _teacher_homework(homework_id, teacher_id)
    if homework.status != PublishStatus.DRAFT.value:
        raise HomeworkConflict("只有草稿作业可以删除")
    db.session.delete(homework)
    db.session.commit()
    try:
        clear_homework_files(Path(current_app.config["MEDIA_ROOT"]), homework_id)
    except (OSError, ValueError):
        current_app.logger.exception("作业 %s 的附件清理失败", homework_id)


def change_homework_status(homework_id: int, teacher_id: int, status: PublishStatus) -> dict:
    homework = _teacher_homework(homework_id, teacher_id)
    if status is PublishStatus.PUBLISHED:
        if homework.status != PublishStatus.DRAFT.value:
            raise HomeworkConflict("只有草稿作业可以发布")
        if homework.course.status != CourseStatus.PUBLISHED.value:
            raise HomeworkConflict("课程发布后才能发布作业")
        if homework.deadline and homework.deadline <= _now():
            raise HomeworkConflict("截止时间已过，不能发布作业")
        homework.published_at = _now()
        queue_course_notifications(
            homework.course_id,
            f"新作业：{homework.title}",
            f"课程“{homework.course.name}”发布了新作业，请按时完成。",
            category="HOMEWORK",
            sender_id=teacher_id,
            link="/homeworks",
        )
    elif status is PublishStatus.CLOSED:
        if homework.status != PublishStatus.PUBLISHED.value:
            raise HomeworkConflict("只有已发布作业可以关闭")
    homework.status = status.value
    db.session.commit()
    return serialize_homework(homework)


def list_teacher_homeworks(teacher_id: int) -> list[dict]:
    homeworks = db.session.scalars(
        _homework_query()
        .where(Homework.teacher_id == teacher_id)
        .order_by(Homework.created_at.desc(), Homework.id.desc())
    ).unique().all()
    return [serialize_homework(item, include_submission_count=True) for item in homeworks]


def list_student_homeworks(student_id: int) -> list[dict]:
    homeworks = db.session.scalars(
        _homework_query()
        .join(Course, Course.id == Homework.course_id)
        .join(CourseStudent, CourseStudent.course_id == Homework.course_id)
        .where(
            CourseStudent.student_id == student_id,
            CourseStudent.status.is_(True),
            Homework.status.in_((PublishStatus.PUBLISHED.value, PublishStatus.CLOSED.value)),
            Course.status == CourseStatus.PUBLISHED.value,
        )
        .order_by(Homework.deadline.asc(), Homework.published_at.desc(), Homework.id.desc())
    ).unique().all()
    return [serialize_homework(item, student_id=student_id) for item in homeworks]


def get_visible_homework(homework_id: int, user_id: int, role: str) -> dict:
    homework = _get_homework(homework_id)
    if role == UserRole.TEACHER.value:
        if homework.teacher_id != user_id:
            raise HomeworkPermissionDenied("不能查看其他教师的作业")
        return serialize_homework(homework, include_submission_count=True)
    if role == UserRole.STUDENT.value:
        _ensure_student_access(homework, user_id)
        return serialize_homework(homework, student_id=user_id)
    raise HomeworkPermissionDenied("无权查看该作业")


def get_homework_attachment_path(homework_id: int, user_id: int, role: str) -> Path:
    homework = _get_homework(homework_id)
    if role == UserRole.TEACHER.value:
        if homework.teacher_id != user_id:
            raise HomeworkPermissionDenied("不能查看其他教师的作业附件")
    elif role == UserRole.STUDENT.value:
        _ensure_student_access(homework, user_id)
    else:
        raise HomeworkPermissionDenied("无权查看作业附件")
    return _checked_attachment_path(homework.attachment)


def get_submission_attachment_path(submission_id: int, user_id: int, role: str) -> Path:
    submission = db.session.scalar(
        db.select(HomeworkSubmission)
        .options(joinedload(HomeworkSubmission.homework))
        .where(HomeworkSubmission.id == submission_id)
    )
    if submission is None:
        raise HomeworkNotFound("作业提交不存在")
    if role == UserRole.TEACHER.value:
        if submission.homework.teacher_id != user_id:
            raise HomeworkPermissionDenied("不能查看其他教师课程的提交附件")
    elif role == UserRole.STUDENT.value:
        if submission.student_id != user_id:
            raise HomeworkPermissionDenied("不能查看其他学生的提交附件")
    else:
        raise HomeworkPermissionDenied("无权查看提交附件")
    return _checked_attachment_path(submission.attachment)


def submit_homework(homework_id: int, student_id: int, content: str) -> dict:
    homework = _get_homework(homework_id)
    _ensure_student_access(homework, student_id)
    if homework.status != PublishStatus.PUBLISHED.value:
        raise HomeworkConflict("作业已关闭，不能继续提交")
    if homework.deadline and _now() > homework.deadline:
        raise HomeworkConflict("作业已超过截止时间")
    submission = db.session.scalar(
        db.select(HomeworkSubmission).where(
            HomeworkSubmission.homework_id == homework.id,
            HomeworkSubmission.student_id == student_id,
        )
    )
    if submission is None:
        submission = HomeworkSubmission(homework_id=homework.id, student_id=student_id)
        db.session.add(submission)
    submission.content = content
    _mark_submitted(submission)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise HomeworkConflict("作业提交冲突，请重试") from exc
    return serialize_submission(submission)


def attach_homework_file(homework_id: int, teacher_id: int, file) -> dict:
    homework = _teacher_homework(homework_id, teacher_id)
    if homework.status != PublishStatus.DRAFT.value:
        raise HomeworkConflict("只有草稿作业可以更换附件")
    relative_path, absolute_path = _save_attachment(file, homework.id, "teacher")
    previous = homework.attachment
    homework.attachment = relative_path
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        absolute_path.unlink(missing_ok=True)
        raise
    _remove_previous_attachment(previous)
    return serialize_homework(_get_homework(homework.id))


def attach_submission_file(homework_id: int, student_id: int, file) -> dict:
    homework = _get_homework(homework_id)
    _ensure_student_access(homework, student_id)
    if homework.status != PublishStatus.PUBLISHED.value:
        raise HomeworkConflict("作业已关闭，不能继续提交")
    if homework.deadline and _now() > homework.deadline:
        raise HomeworkConflict("作业已超过截止时间")
    submission = db.session.scalar(
        db.select(HomeworkSubmission).where(
            HomeworkSubmission.homework_id == homework.id,
            HomeworkSubmission.student_id == student_id,
        )
    )
    if submission is None:
        submission = HomeworkSubmission(homework_id=homework.id, student_id=student_id)
        db.session.add(submission)
        db.session.flush()
    relative_path, absolute_path = _save_attachment(file, homework.id, str(student_id))
    previous = submission.attachment
    submission.attachment = relative_path
    _mark_submitted(submission)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        absolute_path.unlink(missing_ok=True)
        raise
    _remove_previous_attachment(previous)
    return serialize_submission(submission)


def list_submissions(homework_id: int, teacher_id: int) -> list[dict]:
    _teacher_homework(homework_id, teacher_id)
    submissions = db.session.scalars(
        db.select(HomeworkSubmission)
        .options(joinedload(HomeworkSubmission.student))
        .where(HomeworkSubmission.homework_id == homework_id)
        .order_by(HomeworkSubmission.submit_time.desc(), HomeworkSubmission.id.desc())
    ).all()
    return [serialize_submission(item) for item in submissions]


def grade_submission(submission_id: int, teacher_id: int, score: float, comment: str | None) -> dict:
    submission = db.session.scalar(
        db.select(HomeworkSubmission)
        .options(
            joinedload(HomeworkSubmission.student),
            joinedload(HomeworkSubmission.homework),
        )
        .where(HomeworkSubmission.id == submission_id)
    )
    if submission is None:
        raise HomeworkNotFound("作业提交不存在")
    if submission.homework.teacher_id != teacher_id:
        raise HomeworkPermissionDenied("不能批改其他教师课程的作业")
    if submission.homework.status == PublishStatus.DRAFT.value:
        raise HomeworkConflict("未发布作业不能批改")
    if score > float(submission.homework.total_score):
        raise HomeworkConflict("得分不能超过作业满分")
    submission.score = score
    submission.teacher_comment = comment
    submission.status = "GRADED"
    submission.graded_time = _now()
    queue_notification(
        submission.student_id,
        f"作业已批改：{submission.homework.title}",
        f"你的作业已完成批改，得分 {float(score):g}/{float(submission.homework.total_score):g}。",
        category="HOMEWORK",
        sender_id=teacher_id,
        link="/homeworks",
    )
    db.session.commit()
    return serialize_submission(submission)


def serialize_homework(
    homework: Homework,
    student_id: int | None = None,
    include_submission_count: bool = False,
) -> dict:
    payload = {
        "id": homework.id,
        "course_id": homework.course_id,
        "course_name": homework.course.name if homework.course else None,
        "teacher_id": homework.teacher_id,
        "teacher_name": homework.teacher.real_name if homework.teacher else None,
        "title": homework.title,
        "description": homework.description,
        "attachment": homework.attachment,
        "deadline": iso_utc(homework.deadline),
        "total_score": float(homework.total_score),
        "status": homework.status,
        "published_at": iso_utc(homework.published_at),
        "created_at": iso_utc(homework.created_at),
        "updated_at": iso_utc(homework.updated_at),
    }
    if student_id is not None:
        submission = next((item for item in homework.submissions if item.student_id == student_id), None)
        payload["submission"] = serialize_submission(submission) if submission else None
    if include_submission_count:
        payload["submission_count"] = len(homework.submissions)
    return payload


def serialize_submission(submission: HomeworkSubmission) -> dict:
    return {
        "id": submission.id,
        "homework_id": submission.homework_id,
        "student_id": submission.student_id,
        "student_name": submission.student.real_name if submission.student else None,
        "content": submission.content,
        "attachment": submission.attachment,
        "status": submission.status,
        "score": float(submission.score) if submission.score is not None else None,
        "teacher_comment": submission.teacher_comment,
        "submit_time": iso_utc(submission.submit_time),
        "graded_time": iso_utc(submission.graded_time),
    }


def _homework_query():
    return db.select(Homework).options(
        joinedload(Homework.course),
        joinedload(Homework.teacher),
        selectinload(Homework.submissions).joinedload(HomeworkSubmission.student),
    )


def _get_homework(homework_id: int) -> Homework:
    homework = db.session.scalar(_homework_query().where(Homework.id == homework_id))
    if homework is None:
        raise HomeworkNotFound("作业不存在")
    return homework


def _teacher_homework(homework_id: int, teacher_id: int) -> Homework:
    homework = _get_homework(homework_id)
    if homework.teacher_id != teacher_id:
        raise HomeworkPermissionDenied("不能操作其他教师的作业")
    return homework


def _teacher_course(course_id: int, teacher_id: int) -> Course:
    course = db.session.get(Course, course_id)
    if course is None:
        raise HomeworkNotFound("课程不存在")
    if course.teacher_id != teacher_id:
        raise HomeworkPermissionDenied("不能操作其他教师的课程")
    return course


def _ensure_student_access(homework: Homework, student_id: int) -> None:
    if (
        homework.status not in (PublishStatus.PUBLISHED.value, PublishStatus.CLOSED.value)
        or homework.course.status != CourseStatus.PUBLISHED.value
    ):
        raise HomeworkNotFound("作业不存在或尚未发布")
    joined = db.session.scalar(
        db.select(CourseStudent.id).where(
            CourseStudent.course_id == homework.course_id,
            CourseStudent.student_id == student_id,
            CourseStudent.status.is_(True),
        )
    )
    if joined is None:
        raise HomeworkPermissionDenied("请先加入课程")


def _now():
    return utc_now()


def _mark_submitted(submission: HomeworkSubmission) -> None:
    submission.status = "SUBMITTED"
    submission.score = None
    submission.teacher_comment = None
    submission.graded_time = None
    submission.submit_time = _now()


def _save_attachment(file, homework_id: int, owner: str) -> tuple[str, Path]:
    media_root = Path(current_app.config["MEDIA_ROOT"])
    target = save_homework_attachment(
        file,
        media_root / "homework" / str(homework_id) / owner,
        current_app.config["HOMEWORK_ATTACHMENT_MAX_LENGTH"],
    )
    return target.relative_to(media_root).as_posix(), target


def _remove_previous_attachment(relative_path: str | None) -> None:
    try:
        remove_media_file(Path(current_app.config["MEDIA_ROOT"]), relative_path)
    except ValueError:
        current_app.logger.warning("忽略媒体目录之外的历史附件路径：%s", relative_path)


def _checked_attachment_path(relative_path: str | None) -> Path:
    if not relative_path:
        raise HomeworkNotFound("附件不存在")
    media_root = Path(current_app.config["MEDIA_ROOT"]).resolve()
    target = (media_root / relative_path).resolve()
    if target == media_root or not target.is_relative_to(media_root) or not target.is_file():
        raise HomeworkNotFound("附件不存在")
    return target
