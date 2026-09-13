from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from flask import current_app

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.constants import CourseStatus, PublishStatus, UserRole
from app.datetime_utils import iso_utc, utc_now
from app.extensions import db
from app.models import Course, CourseStudent, Exam, ExamAnswer, ExamQuestion, ExamRecord
from app.services.notification_service import queue_course_notifications
from app.services.file_service import remove_media_file, save_homework_attachment


class ExamNotFound(ValueError):
    pass


class ExamPermissionDenied(PermissionError):
    pass


class ExamConflict(ValueError):
    pass


class ExamAttachmentError(ValueError):
    pass


def attach_exam_file(exam_id: int, teacher_id: int, file) -> dict:
    exam = _teacher_exam(exam_id, teacher_id)
    _require_draft(exam)
    root = Path(current_app.config["MEDIA_ROOT"])
    try:
        target = save_homework_attachment(
            file, root / "exams" / str(exam.id),
            current_app.config["EXAM_ATTACHMENT_MAX_LENGTH"],
        )
    except ValueError as exc:
        raise ExamAttachmentError(str(exc)) from exc
    previous = exam.attachment
    exam.attachment = target.relative_to(root).as_posix()
    exam.attachment_name = Path(str(file.filename).replace("\\", "/")).name.strip()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        target.unlink(missing_ok=True)
        raise
    _remove_exam_attachment(previous)
    return serialize_exam(exam, reveal_answers=True)


def remove_exam_attachment(exam_id: int, teacher_id: int) -> dict:
    exam = _teacher_exam(exam_id, teacher_id)
    _require_draft(exam)
    previous = exam.attachment
    exam.attachment = None
    exam.attachment_name = None
    db.session.commit()
    _remove_exam_attachment(previous)
    return serialize_exam(exam, reveal_answers=True)


def get_exam_attachment(exam_id: int, user_id: int, role: str) -> tuple[Path, str]:
    exam = _get_exam(exam_id)
    if role == UserRole.TEACHER.value:
        if exam.teacher_id != user_id:
            raise ExamPermissionDenied("不能查看其他教师的测验附件")
    elif role == UserRole.STUDENT.value:
        _ensure_student_access(exam, user_id)
    else:
        raise ExamPermissionDenied("无权查看测验附件")
    root = Path(current_app.config["MEDIA_ROOT"]).resolve()
    target = (root / (exam.attachment or "")).resolve()
    if not exam.attachment or target == root or not target.is_relative_to(root) or not target.is_file():
        raise ExamNotFound("附件不存在")
    return target, exam.attachment_name or target.name


def _remove_exam_attachment(path: str | None) -> None:
    try:
        remove_media_file(Path(current_app.config["MEDIA_ROOT"]), path)
    except (OSError, ValueError):
        current_app.logger.exception("测验附件清理失败，保留原文件；数据库已保存")


def create_exam(teacher_id: int, data: dict) -> dict:
    course = _teacher_course(data["course_id"], teacher_id)
    if course.status == CourseStatus.OFFLINE.value:
        raise ExamConflict("下线课程不能创建测验")
    exam = Exam(teacher_id=teacher_id, **data)
    db.session.add(exam)
    db.session.commit()
    return serialize_exam(_get_exam(exam.id), reveal_answers=True)


def update_exam(exam_id: int, teacher_id: int, data: dict) -> dict:
    exam = _teacher_exam(exam_id, teacher_id)
    _require_draft(exam)
    if "course_id" in data:
        course = _teacher_course(data["course_id"], teacher_id)
        if course.status == CourseStatus.OFFLINE.value:
            raise ExamConflict("下线课程不能设置测验")
    for field, value in data.items():
        setattr(exam, field, value)
    _validate_time_window(exam)
    db.session.commit()
    return serialize_exam(_get_exam(exam.id), reveal_answers=True)


def delete_draft_exam(exam_id: int, teacher_id: int) -> None:
    exam = _teacher_exam(exam_id, teacher_id)
    _require_draft(exam)
    attachment = exam.attachment
    db.session.delete(exam)
    db.session.commit()
    _remove_exam_attachment(attachment)


def add_question(exam_id: int, teacher_id: int, data: dict) -> dict:
    exam = _teacher_exam(exam_id, teacher_id)
    _require_draft(exam)
    question = ExamQuestion(exam_id=exam.id, **data)
    db.session.add(question)
    db.session.commit()
    return serialize_question(question, reveal_answer=True)


def update_question(question_id: int, teacher_id: int, data: dict) -> dict:
    question = _get_question(question_id)
    if question.exam.teacher_id != teacher_id:
        raise ExamPermissionDenied("不能操作其他教师的试题")
    _require_draft(question.exam)
    for field, value in data.items():
        setattr(question, field, value)
    db.session.commit()
    return serialize_question(question, reveal_answer=True)


def delete_question(question_id: int, teacher_id: int) -> None:
    question = _get_question(question_id)
    if question.exam.teacher_id != teacher_id:
        raise ExamPermissionDenied("不能操作其他教师的试题")
    _require_draft(question.exam)
    db.session.delete(question)
    db.session.commit()


def change_exam_status(exam_id: int, teacher_id: int, status: PublishStatus) -> dict:
    exam = _teacher_exam(exam_id, teacher_id)
    if status is PublishStatus.PUBLISHED:
        _require_draft(exam)
        if exam.course.status != CourseStatus.PUBLISHED.value:
            raise ExamConflict("课程发布后才能发布测验")
        _validate_time_window(exam)
        if exam.end_time and exam.end_time <= _now():
            raise ExamConflict("结束时间已过，不能发布测验")
        if not exam.questions:
            raise ExamConflict("请至少添加一道试题")
        question_total = sum((item.score for item in exam.questions), Decimal("0"))
        if question_total != exam.total_score:
            raise ExamConflict(
                f"试题分值合计为{float(question_total):g}，应与测验总分{float(exam.total_score):g}一致"
            )
        exam.published_at = _now()
        queue_course_notifications(
            exam.course_id,
            f"新测验：{exam.title}",
            f"课程“{exam.course.name}”发布了新测验，请在规定时间内完成。",
            category="EXAM",
            sender_id=teacher_id,
            link="/exams",
        )
    elif status is PublishStatus.CLOSED:
        if exam.status != PublishStatus.PUBLISHED.value:
            raise ExamConflict("只有已发布测验可以关闭")
    exam.status = status.value
    db.session.commit()
    return serialize_exam(exam, reveal_answers=True, include_record_count=True)


def list_teacher_exams(teacher_id: int) -> list[dict]:
    exams = db.session.scalars(
        _exam_query()
        .where(Exam.teacher_id == teacher_id)
        .order_by(Exam.created_at.desc(), Exam.id.desc())
    ).unique().all()
    return [serialize_exam(item, reveal_answers=True, include_record_count=True) for item in exams]


def list_student_exams(student_id: int) -> list[dict]:
    exams = db.session.scalars(
        _exam_query()
        .join(Course, Course.id == Exam.course_id)
        .join(CourseStudent, CourseStudent.course_id == Exam.course_id)
        .where(
            CourseStudent.student_id == student_id,
            CourseStudent.status.is_(True),
            Exam.status.in_((PublishStatus.PUBLISHED.value, PublishStatus.CLOSED.value)),
            Course.status == CourseStatus.PUBLISHED.value,
        )
        .order_by(Exam.start_time.asc(), Exam.published_at.desc(), Exam.id.desc())
    ).unique().all()
    changed = False
    for exam in exams:
        record = next((item for item in exam.records if item.student_id == student_id), None)
        if record and record.status == "DOING" and _record_expired(record):
            _finalize_record(record, _saved_answers(record), submitted_at=_record_deadline(record))
            changed = True
    if changed:
        db.session.commit()
    return [serialize_exam(item, student_id=student_id) for item in exams]


def get_visible_exam(exam_id: int, user_id: int, role: str) -> dict:
    exam = _get_exam(exam_id)
    if role == UserRole.TEACHER.value:
        if exam.teacher_id != user_id:
            raise ExamPermissionDenied("不能查看其他教师的测验")
        return serialize_exam(exam, reveal_answers=True, include_record_count=True)
    if role == UserRole.STUDENT.value:
        _ensure_student_access(exam, user_id)
        record = _student_record(exam.id, user_id)
        if record is not None and record.status == "DOING" and _record_expired(record):
            _finalize_record(record, _saved_answers(record), submitted_at=_record_deadline(record))
            db.session.commit()
        reveal_answers = record is not None and record.status == "SUBMITTED"
        return serialize_exam(exam, student_id=user_id, reveal_answers=reveal_answers)
    raise ExamPermissionDenied("无权查看该测验")


def start_exam(exam_id: int, student_id: int) -> dict:
    exam = _get_exam(exam_id)
    _ensure_student_access(exam, student_id)
    existing = _student_record(exam.id, student_id)
    if existing is not None:
        if existing.status == "SUBMITTED":
            raise ExamConflict("该测验已经正式提交，不能重复作答")
        if _record_expired(existing):
            _finalize_record(existing, _saved_answers(existing), submitted_at=_record_deadline(existing))
            db.session.commit()
        else:
            _ensure_can_take(exam, student_id)
        return serialize_record(existing, include_answers=existing.status == "SUBMITTED")
    _ensure_can_take(exam, student_id)
    record = ExamRecord(
        exam_id=exam.id,
        student_id=student_id,
        status="DOING",
        started_at=_now(),
    )
    db.session.add(record)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ExamConflict("测验开始冲突，请刷新后重试") from exc
    return serialize_record(_get_record(record.id), include_answers=False)


def save_exam_answers(exam_id: int, student_id: int, submitted_answers: dict[int, str]) -> dict:
    exam = _get_exam(exam_id)
    _ensure_student_access(exam, student_id)
    if exam.status != PublishStatus.PUBLISHED.value:
        raise ExamConflict("测验已关闭，不能保存答案")
    record = _student_record(exam.id, student_id, for_update=True)
    if record is None:
        raise ExamConflict("请先开始测验")
    if record.status == "SUBMITTED":
        raise ExamConflict("该测验已经提交，不能修改答案")
    _ensure_record_time(record)

    _validate_submitted_questions(exam, submitted_answers)
    _store_answers(record, submitted_answers, grade=False)
    db.session.commit()
    return serialize_record(_get_record(record.id), include_answers=False)


def submit_exam(exam_id: int, student_id: int, submitted_answers: dict[int, str]) -> dict:
    exam = _get_exam(exam_id)
    _ensure_student_access(exam, student_id)
    record = _student_record(exam.id, student_id, for_update=True)
    if record is None:
        raise ExamConflict("请先开始测验")
    if record.status == "SUBMITTED":
        raise ExamConflict("该测验已经正式提交")

    expired = _record_expired(record)
    if not expired and exam.status != PublishStatus.PUBLISHED.value:
        raise ExamConflict("测验已关闭，不能继续提交")
    if expired:
        submitted_answers = _saved_answers(record)
    else:
        _validate_submitted_questions(exam, submitted_answers)

    _finalize_record(
        record,
        submitted_answers,
        submitted_at=_record_deadline(record) if expired else None,
    )
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ExamConflict("测验已经提交或提交发生冲突") from exc
    return serialize_record(_get_record(record.id), include_answers=True)


def _validate_submitted_questions(exam: Exam, submitted_answers: dict[int, str]) -> None:
    question_ids = {question.id for question in exam.questions}
    if set(submitted_answers) - question_ids:
        raise ExamConflict("答案中包含不属于该测验的试题")


def _store_answers(record: ExamRecord, submitted_answers: dict[int, str], *, grade: bool) -> dict[int, ExamAnswer]:
    questions = {question.id: question for question in record.exam.questions}
    existing = {answer.question_id: answer for answer in record.answers}
    for question_id, raw_answer in submitted_answers.items():
        question = questions[question_id]
        normalized = raw_answer.strip().upper() if raw_answer else None
        answer = existing.get(question_id)
        if answer is None:
            answer = ExamAnswer(exam_record_id=record.id, question_id=question_id)
            db.session.add(answer)
            existing[question_id] = answer
        answer.student_answer = normalized
        if grade:
            answer.is_correct = normalized == question.correct_answer.upper()
            answer.score = question.score if answer.is_correct else Decimal("0")
        else:
            answer.is_correct = False
            answer.score = Decimal("0")
    return existing


def _saved_answers(record: ExamRecord) -> dict[int, str]:
    return {item.question_id: item.student_answer or "" for item in record.answers}


def _finalize_record(
    record: ExamRecord,
    submitted_answers: dict[int, str],
    *,
    submitted_at=None,
) -> None:
    _validate_submitted_questions(record.exam, submitted_answers)
    by_question = _store_answers(record, submitted_answers, grade=True)

    total = Decimal("0")
    correct_count = 0
    for question in record.exam.questions:
        answer = by_question.get(question.id)
        if answer and answer.is_correct:
            correct_count += 1
            total += answer.score

    now = submitted_at or _now()
    record.score = total
    record.correct_count = correct_count
    record.wrong_count = len(record.exam.questions) - correct_count
    record.status = "SUBMITTED"
    record.submit_time = now
    record.duration_seconds = max(0, int((now - record.started_at).total_seconds()))


def list_exam_records(exam_id: int, teacher_id: int) -> list[dict]:
    _teacher_exam(exam_id, teacher_id)
    records = db.session.scalars(
        _record_query()
        .where(ExamRecord.exam_id == exam_id)
        .order_by(ExamRecord.submit_time.desc(), ExamRecord.id.desc())
    ).unique().all()
    changed = False
    for record in records:
        if record.status == "DOING" and _record_expired(record):
            _finalize_record(record, _saved_answers(record), submitted_at=_record_deadline(record))
            changed = True
    if changed:
        db.session.commit()
    return [serialize_record(item, include_answers=item.status == "SUBMITTED") for item in records]


def get_visible_record(record_id: int, user_id: int, role: str) -> dict:
    record = _get_record(record_id)
    if record.status == "DOING" and _record_expired(record):
        _finalize_record(record, _saved_answers(record), submitted_at=_record_deadline(record))
        db.session.commit()
    if role == UserRole.TEACHER.value and record.exam.teacher_id == user_id:
        return serialize_record(record, include_answers=record.status == "SUBMITTED")
    if role == UserRole.STUDENT.value and record.student_id == user_id:
        return serialize_record(record, include_answers=record.status == "SUBMITTED")
    raise ExamPermissionDenied("无权查看该测验记录")


def serialize_exam(
    exam: Exam,
    student_id: int | None = None,
    reveal_answers: bool = False,
    include_record_count: bool = False,
) -> dict:
    payload = {
        "id": exam.id,
        "course_id": exam.course_id,
        "course_name": exam.course.name if exam.course else None,
        "teacher_id": exam.teacher_id,
        "teacher_name": exam.teacher.real_name if exam.teacher else None,
        "title": exam.title,
        "description": exam.description,
        "attachment": exam.attachment,
        "attachment_name": exam.attachment_name,
        "total_score": float(exam.total_score),
        "status": exam.status,
        "start_time": _iso(exam.start_time),
        "end_time": _iso(exam.end_time),
        "time_limit_minutes": exam.time_limit_minutes,
        "published_at": _iso(exam.published_at),
        "created_at": _iso(exam.created_at),
        "updated_at": _iso(exam.updated_at),
        "availability": _availability(exam),
        "questions": [
            serialize_question(item, reveal_answer=reveal_answers)
            for item in sorted(exam.questions, key=lambda value: (value.sort_order, value.id))
        ],
    }
    if student_id is not None:
        record = next((item for item in exam.records if item.student_id == student_id), None)
        payload["record"] = (
            serialize_record(record, include_answers=record.status == "SUBMITTED") if record else None
        )
    if include_record_count:
        payload["record_count"] = len(exam.records)
        payload["submitted_count"] = sum(item.status == "SUBMITTED" for item in exam.records)
    return payload


def serialize_question(question: ExamQuestion, reveal_answer: bool = False) -> dict:
    payload = {
        "id": question.id,
        "exam_id": question.exam_id,
        "question_type": question.question_type,
        "content": question.content,
        "options": {
            key: value
            for key, value in {
                "A": question.option_a,
                "B": question.option_b,
                "C": question.option_c,
                "D": question.option_d,
            }.items()
            if value is not None
        },
        "score": float(question.score),
        "sort_order": question.sort_order,
    }
    if reveal_answer:
        payload["correct_answer"] = question.correct_answer
    return payload


def serialize_record(record: ExamRecord, include_answers: bool) -> dict:
    payload = {
        "id": record.id,
        "exam_id": record.exam_id,
        "exam_title": record.exam.title if record.exam else None,
        "student_id": record.student_id,
        "student_name": record.student.real_name if record.student else None,
        "score": float(record.score),
        "total_score": float(record.exam.total_score) if record.exam else None,
        "correct_count": record.correct_count,
        "wrong_count": record.wrong_count,
        "status": record.status,
        "started_at": _iso(record.started_at),
        "submit_time": _iso(record.submit_time),
        "duration_seconds": record.duration_seconds,
    }
    if record.status == "DOING":
        payload["draft_answers"] = [
            {"question_id": item.question_id, "answer": item.student_answer or ""}
            for item in record.answers
        ]
        payload["deadline"] = _iso(_record_deadline(record))
    if include_answers:
        by_question = {item.question_id: item for item in record.answers}
        payload["answers"] = []
        for question in sorted(record.exam.questions, key=lambda item: (item.sort_order, item.id)):
            answer = by_question.get(question.id)
            payload["answers"].append(
                {
                    "question": serialize_question(question, reveal_answer=True),
                    "student_answer": answer.student_answer if answer else None,
                    "is_correct": bool(answer.is_correct) if answer else False,
                    "score": float(answer.score) if answer else 0.0,
                }
            )
    return payload


def _exam_query():
    return db.select(Exam).options(
        joinedload(Exam.course),
        joinedload(Exam.teacher),
        selectinload(Exam.questions),
        selectinload(Exam.records).joinedload(ExamRecord.student),
    )


def _record_query():
    return db.select(ExamRecord).options(
        joinedload(ExamRecord.exam).selectinload(Exam.questions),
        joinedload(ExamRecord.student),
        selectinload(ExamRecord.answers).joinedload(ExamAnswer.question),
    )


def _get_exam(exam_id: int) -> Exam:
    exam = db.session.scalar(_exam_query().where(Exam.id == exam_id))
    if exam is None:
        raise ExamNotFound("测验不存在")
    return exam


def _get_question(question_id: int) -> ExamQuestion:
    question = db.session.scalar(
        db.select(ExamQuestion)
        .options(joinedload(ExamQuestion.exam))
        .where(ExamQuestion.id == question_id)
    )
    if question is None:
        raise ExamNotFound("试题不存在")
    return question


def _get_record(record_id: int) -> ExamRecord:
    record = db.session.scalar(_record_query().where(ExamRecord.id == record_id))
    if record is None:
        raise ExamNotFound("测验记录不存在")
    return record


def _student_record(
    exam_id: int,
    student_id: int,
    for_update: bool = False,
) -> ExamRecord | None:
    statement = _record_query().where(
        ExamRecord.exam_id == exam_id,
        ExamRecord.student_id == student_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return db.session.scalar(statement)


def _teacher_exam(exam_id: int, teacher_id: int) -> Exam:
    exam = _get_exam(exam_id)
    if exam.teacher_id != teacher_id:
        raise ExamPermissionDenied("不能操作其他教师的测验")
    return exam


def _teacher_course(course_id: int, teacher_id: int) -> Course:
    course = db.session.get(Course, course_id)
    if course is None:
        raise ExamNotFound("课程不存在")
    if course.teacher_id != teacher_id:
        raise ExamPermissionDenied("不能操作其他教师的课程")
    return course


def _ensure_student_access(exam: Exam, student_id: int) -> None:
    if (
        exam.status not in (PublishStatus.PUBLISHED.value, PublishStatus.CLOSED.value)
        or exam.course.status != CourseStatus.PUBLISHED.value
    ):
        raise ExamNotFound("测验不存在或尚未发布")
    joined = db.session.scalar(
        db.select(CourseStudent.id).where(
            CourseStudent.course_id == exam.course_id,
            CourseStudent.student_id == student_id,
            CourseStudent.status.is_(True),
        )
    )
    if joined is None:
        raise ExamPermissionDenied("请先加入课程")


def _ensure_can_take(exam: Exam, student_id: int) -> None:
    _ensure_student_access(exam, student_id)
    if exam.status != PublishStatus.PUBLISHED.value:
        raise ExamConflict("测验已关闭")
    availability = _availability(exam)
    if availability == "NOT_STARTED":
        raise ExamConflict("测验尚未开始")
    if availability == "ENDED":
        raise ExamConflict("测验已经结束")


def _ensure_record_time(record: ExamRecord) -> None:
    if _record_expired(record):
        raise ExamConflict("作答时间已经结束")


def _record_deadline(record: ExamRecord):
    deadline = record.exam.end_time
    if record.exam.time_limit_minutes and record.started_at:
        limit = record.started_at + timedelta(minutes=record.exam.time_limit_minutes)
        deadline = min(deadline, limit) if deadline else limit
    return deadline


def _record_expired(record: ExamRecord) -> bool:
    deadline = _record_deadline(record)
    return bool(deadline and _now() >= deadline)


def _require_draft(exam: Exam) -> None:
    if exam.status != PublishStatus.DRAFT.value:
        raise ExamConflict("只有草稿测验可以编辑")


def _validate_time_window(exam: Exam) -> None:
    if exam.start_time and exam.end_time and exam.start_time >= exam.end_time:
        raise ExamConflict("测验结束时间必须晚于开始时间")


def _availability(exam: Exam) -> str:
    if exam.status == PublishStatus.CLOSED.value:
        return "CLOSED"
    now = _now()
    if exam.start_time and now < exam.start_time:
        return "NOT_STARTED"
    if exam.end_time and now > exam.end_time:
        return "ENDED"
    return "AVAILABLE" if exam.status == PublishStatus.PUBLISHED.value else "DRAFT"


def _iso(value) -> str | None:
    return iso_utc(value)


def _now():
    return utc_now()
