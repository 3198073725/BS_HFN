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
    TeachingClass,
    TeachingClassCourse,
    TeachingClassStudent,
    User,
    Video,
)


class StatisticsPermissionDenied(PermissionError):
    pass


class StatisticsNotFound(ValueError):
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


def get_teacher_class_statistics(class_id: int, teacher_id: int) -> dict:
    classroom = db.session.get(TeachingClass, class_id)
    if classroom is None:
        raise StatisticsNotFound("班级不存在")
    if classroom.teacher_id != teacher_id:
        raise StatisticsPermissionDenied("不能查看其他教师班级的统计")

    student_ids = db.select(TeachingClassStudent.student_id).where(
        TeachingClassStudent.class_id == class_id
    )
    courses = db.session.scalars(
        db.select(Course)
        .join(TeachingClassCourse, TeachingClassCourse.course_id == Course.id)
        .where(TeachingClassCourse.class_id == class_id)
        .order_by(Course.created_at.desc(), Course.id.desc())
    ).all()
    member_count = _count(db.select(func.count()).select_from(student_ids.subquery()))
    course_rows = [_class_course_statistics(course, student_ids, member_count) for course in courses]

    ready_video_count = sum(item["ready_video_count"] for item in course_rows)
    homework_count = sum(item["homework_count"] for item in course_rows)
    homework_submissions = sum(item["homework_submission_count"] for item in course_rows)
    exam_count = sum(item["exam_count"] for item in course_rows)
    exam_submissions = sum(item["exam_submission_count"] for item in course_rows)
    homework_denominator = member_count * homework_count
    exam_denominator = member_count * exam_count

    return {
        "class_id": classroom.id,
        "class_name": classroom.name,
        "member_count": member_count,
        "course_count": len(course_rows),
        "overview": {
            "average_progress": _weighted_average(
                course_rows,
                "average_progress",
                lambda item: member_count * item["ready_video_count"],
            ),
            "homework_submission_rate": _percentage(homework_submissions, homework_denominator),
            "average_homework_percent": _weighted_average(
                course_rows,
                "average_homework_percent",
                lambda item: item["graded_homework_count"],
            ),
            "exam_completion_rate": _percentage(exam_submissions, exam_denominator),
            "average_exam_percent": _weighted_average(
                course_rows,
                "average_exam_percent",
                lambda item: item["scored_exam_count"],
            ),
            "ready_video_count": ready_video_count,
            "homework_count": homework_count,
            "exam_count": exam_count,
        },
        "courses": course_rows,
    }


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
            func.avg(_exam_score_percent()),
        )
        .select_from(ExamRecord)
        .join(Exam, Exam.id == ExamRecord.exam_id)
        .where(ExamRecord.student_id == student_id, ExamRecord.status.in_(("SUBMITTED", "GRADED")))
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
        .where(Exam.teacher_id == teacher_id, ExamRecord.status.in_(("SUBMITTED", "GRADED")))
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
        "processing_videos": _count(
            db.select(func.count(Video.id)).where(
                Video.status.in_([VideoStatus.PENDING.value, VideoStatus.PROCESSING.value])
            )
        ),
        "failed_videos": _count(
            db.select(func.count(Video.id)).where(Video.status == VideoStatus.FAILED.value)
        ),
        "learning_records": _count(db.select(func.count(LearningRecord.id))),
        "homework_submissions": _count(db.select(func.count(HomeworkSubmission.id))),
        "exam_records": _count(
            db.select(func.count(ExamRecord.id)).where(ExamRecord.status.in_(("SUBMITTED", "GRADED")))
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
        db.select(func.count(ExamRecord.id), func.avg(_exam_score_percent()))
        .select_from(ExamRecord)
        .join(Exam, Exam.id == ExamRecord.exam_id)
        .where(Exam.course_id == course.id, ExamRecord.status.in_(("SUBMITTED", "GRADED")))
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


def _class_course_statistics(course: Course, student_ids, member_count: int) -> dict:
    ready_video_ids = (
        db.select(Video.id)
        .join(Chapter, Chapter.id == Video.chapter_id)
        .where(Chapter.course_id == course.id, Video.status == VideoStatus.READY.value)
    )
    video_count = _count(db.select(func.count()).select_from(ready_video_ids.subquery()))
    enrolled_count = _count(
        db.select(func.count(CourseStudent.id)).where(
            CourseStudent.course_id == course.id,
            CourseStudent.student_id.in_(student_ids),
            CourseStudent.status.is_(True),
        )
    )
    progress_sum = db.session.scalar(
        db.select(func.sum(LearningRecord.progress)).where(
            LearningRecord.student_id.in_(student_ids),
            LearningRecord.video_id.in_(ready_video_ids),
        )
    )

    visible_homework_ids = db.select(Homework.id).where(
        Homework.course_id == course.id,
        Homework.status.in_((PublishStatus.PUBLISHED.value, PublishStatus.CLOSED.value)),
    )
    homework_count = _count(
        db.select(func.count()).select_from(visible_homework_ids.subquery())
    )
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
        .where(
            HomeworkSubmission.student_id.in_(student_ids),
            HomeworkSubmission.homework_id.in_(visible_homework_ids),
        )
    ).one()

    visible_exam_ids = db.select(Exam.id).where(
        Exam.course_id == course.id,
        Exam.status.in_((PublishStatus.PUBLISHED.value, PublishStatus.CLOSED.value)),
    )
    exam_count = _count(db.select(func.count()).select_from(visible_exam_ids.subquery()))
    exam = db.session.execute(
        db.select(
            func.count(ExamRecord.id),
            func.avg(_exam_score_percent()),
            func.count(_exam_score_percent()),
        )
        .select_from(ExamRecord)
        .join(Exam, Exam.id == ExamRecord.exam_id)
        .where(
            ExamRecord.student_id.in_(student_ids),
            ExamRecord.exam_id.in_(visible_exam_ids),
            ExamRecord.status.in_(("SUBMITTED", "GRADED")),
        )
    ).one()

    return {
        "course_id": course.id,
        "course_name": course.name,
        "status": course.status,
        "member_count": member_count,
        "enrolled_count": enrolled_count,
        "ready_video_count": video_count,
        "average_progress": _round(float(progress_sum or 0) / (member_count * video_count))
        if member_count and video_count
        else 0.0,
        "homework_count": homework_count,
        "homework_submission_count": int(homework[0] or 0),
        "homework_submission_rate": _percentage(
            int(homework[0] or 0), member_count * homework_count
        ),
        "graded_homework_count": int(homework[1] or 0),
        "average_homework_percent": _round(homework[2]),
        "exam_count": exam_count,
        "exam_submission_count": int(exam[0] or 0),
        "exam_completion_rate": _percentage(int(exam[0] or 0), member_count * exam_count),
        "average_exam_percent": _round(exam[1]),
        "scored_exam_count": int(exam[2] or 0),
    }


def _exam_score_percent():
    return db.case(
        (Exam.exam_type == "ONLINE", ExamRecord.score * 100.0 / Exam.total_score),
        (ExamRecord.status == "GRADED", ExamRecord.score * 100.0 / Exam.total_score),
        else_=None,
    )


def _percentage(numerator: int, denominator: int) -> float:
    return _round(numerator * 100.0 / denominator) if denominator else 0.0


def _weighted_average(items: list[dict], field: str, weight) -> float:
    denominator = sum(weight(item) for item in items)
    if not denominator:
        return 0.0
    numerator = sum(float(item[field]) * weight(item) for item in items)
    return _round(numerator / denominator)


def _count(statement) -> int:
    return int(db.session.scalar(statement) or 0)


def _round(value) -> float:
    return round(float(value or 0), 2)
