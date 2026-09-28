from sqlalchemy import and_, exists, not_, or_

from app.extensions import db
from app.models import CourseStudent, TeachingClassCourse, TeachingClassStudent


def class_task_access_condition(course_id, student_id):
    """Allow standalone courses or approved membership in an assigned class."""
    assigned_to_class = exists(
        db.select(TeachingClassCourse.id).where(
            TeachingClassCourse.course_id == course_id,
        )
    )
    approved_class_membership = exists(
        db.select(TeachingClassCourse.id)
        .join(
            TeachingClassStudent,
            TeachingClassStudent.class_id == TeachingClassCourse.class_id,
        )
        .where(
            TeachingClassCourse.course_id == course_id,
            TeachingClassStudent.student_id == student_id,
        )
    )
    return or_(not_(assigned_to_class), approved_class_membership)


def course_task_access_condition(course_id, student_id: int):
    """Require approved class membership when a course is assigned to a class.

    Standalone courses keep their normal CourseStudent access.  Once a course is
    attached to one or more teaching classes, an active course enrollment alone
    is insufficient: the student must be an actual member of one of those
    classes.  A pending/rejected/cancelled join request never grants access.
    """
    active_course_enrollment = exists(
        db.select(CourseStudent.id).where(
            CourseStudent.course_id == course_id,
            CourseStudent.student_id == student_id,
            CourseStudent.status.is_(True),
        )
    )
    return and_(
        active_course_enrollment,
        class_task_access_condition(course_id, student_id),
    )


def student_can_access_course_tasks(course_id: int, student_id: int) -> bool:
    return bool(
        db.session.scalar(
            db.select(course_task_access_condition(course_id, student_id))
        )
    )
