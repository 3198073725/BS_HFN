from sqlalchemy import distinct, func

from app.constants import CourseStatus, PublishStatus, QuestionStatus, UserRole, VideoStatus
from app.extensions import db
from app.models import (
    Chapter,
    Course,
    CourseStudent,
    Exam,
    ExamRecord,
    Homework,
    HomeworkSubmission,
    LearningRecord,
    Question,
    User,
    Video,
)


class StatisticsPermissionDenied(PermissionError):
    pass


def get_overview(user_id: int, role: str) -> dict:
    if role == UserRole.STUDENT.value:
        return _student_overview(user_id)
    if role == UserRole.TEACHER.value:
        return _teacher_overview(user_id)
    if role == UserRole.ADMIN.value:
        return _admin_overview()
    raise StatisticsPermissionDenied("无权查看统计数据")


def get_teacher_course_statistics(teacher_id: int) -> list[dict]:
    courses = db.session.scalars(
        db.select(Course)
        .where(Course.teacher_id == teacher_id)
        .order_by(Course.created_at.desc(), Course.id.desc())
    ).all()
    return [_course_statistics(course) for course in courses]


def _student_overview(student_id: int) -> dict:
    joined_courses = _count(
        db.select(func.count(CourseStudent.id)).where(
            CourseStudent.student_id == student_id,
            CourseStudent.status.is_(True),
        )
    )
    learning = db.session.execute(
        db.select(
            func.count(LearningRecord.id),
            func.sum(db.case((LearningRecord.status == "COMPLETED", 1), else_=0)),
            func.avg(LearningRecord.progress),
            func.sum(LearningRecord.watch_duration),
        ).where(LearningRecord.student_id == student_id)
    ).one()
    homework = db.session.execute(
        db.select(
            func.count(HomeworkSubmission.id),
            func.sum(db.case((HomeworkSubmission.status == "GRADED", 1), else_=0)),
            func.avg(
                db.case(
                    (
                        HomeworkSubmission.status == "GRADED",
                        HomeworkSubmission.score * 100.0 / Homework.total_score,
                    ),
                    else_=None,
                )
            ),
        )
        .select_from(HomeworkSubmission)
        .join(Homework, Homework.id == HomeworkSubmission.homework_id)
        .where(HomeworkSubmission.student_id == student_id)
    ).one()
    exam = db.session.execute(
        db.select(
            func.count(ExamRecord.id),
            func.avg(ExamRecord.score * 100.0 / Exam.total_score),
        )
        .select_from(ExamRecord)
        .join(Exam, Exam.id == ExamRecord.exam_id)
        .where(ExamRecord.student_id == student_id, ExamRecord.status == "SUBMITTED")
    ).one()
    return {
        "role": UserRole.STUDENT.value,
        "joined_courses": joined_courses,
        "learned_videos": int(learning[0] or 0),
        "completed_videos": int(learning[1] or 0),
        "average_video_progress": _round(learning[2]),
        "watch_duration_seconds": int(learning[3] or 0),
        "submitted_homeworks": int(homework[0] or 0),
        "graded_homeworks": int(homework[1] or 0),
        "average_homework_percent": _round(homework[2]),
        "completed_exams": int(exam[0] or 0),
        "average_exam_percent": _round(exam[1]),
    }


def _teacher_overview(teacher_id: int) -> dict:
    course_ids = db.select(Course.id).where(Course.teacher_id == teacher_id)
    course_count = _count(db.select(func.count(Course.id)).where(Course.teacher_id == teacher_id))
    published_courses = _count(
        db.select(func.count(Course.id)).where(
            Course.teacher_id == teacher_id,
            Course.status == CourseStatus.PUBLISHED.value,
        )
    )
    students = _count(
        db.select(func.count(distinct(CourseStudent.student_id))).where(
            CourseStudent.course_id.in_(course_ids),
            CourseStudent.status.is_(True),
        )
    )
    ready_videos = _count(
        db.select(func.count(Video.id))
        .select_from(Video)
        .join(Chapter, Chapter.id == Video.chapter_id)
        .where(
            Chapter.course_id.in_(course_ids),
            Video.status == VideoStatus.READY.value,
        )
    )
    waiting_questions = _count(
        db.select(func.count(Question.id))
        .select_from(Question)
        .join(Video, Video.id == Question.video_id)
        .join(Chapter, Chapter.id == Video.chapter_id)
        .where(
            Chapter.course_id.in_(course_ids),
            Question.status == QuestionStatus.WAITING.value,
        )
    )
    ungraded_submissions = _count(
        db.select(func.count(HomeworkSubmission.id))
        .select_from(HomeworkSubmission)
        .join(Homework, Homework.id == HomeworkSubmission.homework_id)
        .where(Homework.teacher_id == teacher_id, HomeworkSubmission.status == "SUBMITTED")
    )
    submitted_exams = _count(
        db.select(func.count(ExamRecord.id))
        .select_from(ExamRecord)
        .join(Exam, Exam.id == ExamRecord.exam_id)
        .where(Exam.teacher_id == teacher_id, ExamRecord.status == "SUBMITTED")
    )
    return {
        "role": UserRole.TEACHER.value,
        "courses": course_count,
        "published_courses": published_courses,
        "active_students": students,
        "ready_videos": ready_videos,
        "waiting_questions": waiting_questions,
        "ungraded_homeworks": ungraded_submissions,
        "submitted_exams": submitted_exams,
    }


def _admin_overview() -> dict:
    role_counts = {
        role: _count(db.select(func.count(User.id)).where(User.role == role))
        for role in (UserRole.STUDENT.value, UserRole.TEACHER.value, UserRole.ADMIN.value)
    }
    return {
        "role": UserRole.ADMIN.value,
        "users": sum(role_counts.values()),
        "active_users": _count(db.select(func.count(User.id)).where(User.status.is_(True))),
        "students": role_counts[UserRole.STUDENT.value],
        "teachers": role_counts[UserRole.TEACHER.value],
        "administrators": role_counts[UserRole.ADMIN.value],
        "courses": _count(db.select(func.count(Course.id))),
        "published_courses": _count(
            db.select(func.count(Course.id)).where(Course.status == CourseStatus.PUBLISHED.value)
        ),
        "ready_videos": _count(
            db.select(func.count(Video.id)).where(Video.status == VideoStatus.READY.value)
        ),
        "learning_records": _count(db.select(func.count(LearningRecord.id))),
        "homework_submissions": _count(db.select(func.count(HomeworkSubmission.id))),
        "exam_records": _count(
            db.select(func.count(ExamRecord.id)).where(ExamRecord.status == "SUBMITTED")
        ),
    }


def _course_statistics(course: Course) -> dict:
    active_student_ids = db.select(CourseStudent.student_id).where(
        CourseStudent.course_id == course.id,
        CourseStudent.status.is_(True),
    )
    ready_video_ids = (
        db.select(Video.id)
        .join(Chapter, Chapter.id == Video.chapter_id)
        .where(Chapter.course_id == course.id, Video.status == VideoStatus.READY.value)
    )
    student_count = _count(db.select(func.count()).select_from(active_student_ids.subquery()))
    video_count = _count(db.select(func.count()).select_from(ready_video_ids.subquery()))
    progress_sum = db.session.scalar(
        db.select(func.sum(LearningRecord.progress)).where(
            LearningRecord.student_id.in_(active_student_ids),
            LearningRecord.video_id.in_(ready_video_ids),
        )
    )
    denominator = student_count * video_count
    homework = db.session.execute(
        db.select(
            func.count(HomeworkSubmission.id),
            func.avg(
                db.case(
                    (
                        HomeworkSubmission.status == "GRADED",
                        HomeworkSubmission.score * 100.0 / Homework.total_score,
                    ),
                    else_=None,
                )
            ),
        )
        .select_from(HomeworkSubmission)
        .join(Homework, Homework.id == HomeworkSubmission.homework_id)
        .where(Homework.course_id == course.id)
    ).one()
    exam = db.session.execute(
        db.select(func.count(ExamRecord.id), func.avg(ExamRecord.score * 100.0 / Exam.total_score))
        .select_from(ExamRecord)
        .join(Exam, Exam.id == ExamRecord.exam_id)
        .where(Exam.course_id == course.id, ExamRecord.status == "SUBMITTED")
    ).one()
    return {
        "course_id": course.id,
        "course_name": course.name,
        "status": course.status,
        "student_count": student_count,
        "ready_video_count": video_count,
        "average_progress": _round(float(progress_sum or 0) / denominator) if denominator else 0.0,
        "homework_submission_count": int(homework[0] or 0),
        "average_homework_percent": _round(homework[1]),
        "exam_submission_count": int(exam[0] or 0),
        "average_exam_percent": _round(exam[1]),
    }


def _count(statement) -> int:
    return int(db.session.scalar(statement) or 0)


def _round(value) -> float:
    return round(float(value or 0), 2)
