from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.constants import CourseStatus, UserRole
from app.datetime_utils import iso_utc, utc_now
from app.extensions import db
from app.models import (
    Course,
    CourseStudent,
    TeachingClass,
    TeachingClassCourse,
    TeachingClassStudent,
    User,
)


class ClassNotFound(ValueError):
    pass


class ClassPermissionDenied(PermissionError):
    pass


class ClassConflict(ValueError):
    pass


def list_course_options(teacher_id: int) -> list[dict]:
    courses = db.session.scalars(
        db.select(Course)
        .options(selectinload(Course.category))
        .where(Course.teacher_id == teacher_id)
        .order_by(Course.created_at.desc(), Course.id.desc())
    ).all()
    return [
        {
            "id": course.id,
            "name": course.name,
            "description": course.description,
            "category_name": course.category.name if course.category else None,
            "status": course.status,
        }
        for course in courses
    ]


def list_classes(user_id: int, role: str) -> list[dict]:
    statement = db.select(TeachingClass).options(
        selectinload(TeachingClass.teacher),
        selectinload(TeachingClass.student_links).selectinload(TeachingClassStudent.student),
        selectinload(TeachingClass.course_links)
        .selectinload(TeachingClassCourse.course)
        .selectinload(Course.category),
    )
    if role == UserRole.TEACHER.value:
        statement = statement.where(TeachingClass.teacher_id == user_id)
    else:
        statement = statement.join(TeachingClassStudent).where(
            TeachingClassStudent.student_id == user_id
        )
    classrooms = db.session.scalars(
        statement.order_by(TeachingClass.created_at.desc(), TeachingClass.id.desc())
    ).all()
    return [
        serialize_classroom(
            classroom,
            include_students=role == UserRole.TEACHER.value,
            viewer_student_id=user_id if role == UserRole.STUDENT.value else None,
        )
        for classroom in classrooms
    ]


def create_classroom(teacher_id: int, data: dict) -> dict:
    _ensure_unique_name(teacher_id, data["name"])
    classroom = TeachingClass(teacher_id=teacher_id, **data)
    db.session.add(classroom)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ClassConflict("你已经创建过同名班级") from exc
    return serialize_classroom(_owned_classroom(classroom.id, teacher_id), include_students=True)


def update_classroom(class_id: int, teacher_id: int, data: dict) -> dict:
    classroom = _owned_classroom(class_id, teacher_id)
    if "name" in data and data["name"] != classroom.name:
        _ensure_unique_name(teacher_id, data["name"], exclude_id=classroom.id)
    for field, value in data.items():
        setattr(classroom, field, value)
    db.session.commit()
    return serialize_classroom(_owned_classroom(classroom.id, teacher_id), include_students=True)


def delete_classroom(class_id: int, teacher_id: int) -> None:
    classroom = _owned_classroom(class_id, teacher_id)
    db.session.delete(classroom)
    db.session.commit()


def add_student(class_id: int, teacher_id: int, account: str) -> dict:
    classroom = _owned_classroom(class_id, teacher_id)
    student = db.session.scalar(
        db.select(User).where(
            or_(
                User.username == account,
                User.student_no == account,
                User.email == account,
            )
        )
    )
    if student is None:
        raise ClassNotFound("没有找到对应的学生账号")
    if student.role != UserRole.STUDENT.value:
        raise ClassConflict("该账号不是学生账号")
    if not student.status:
        raise ClassConflict("该学生账号已被禁用")
    existing = db.session.scalar(
        db.select(TeachingClassStudent).where(
            TeachingClassStudent.class_id == classroom.id,
            TeachingClassStudent.student_id == student.id,
        )
    )
    if existing is not None:
        raise ClassConflict("该学生已经在班级中")
    db.session.add(TeachingClassStudent(class_id=classroom.id, student_id=student.id))
    _enroll_student_in_class_courses(classroom, student.id)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ClassConflict("该学生已经在班级中") from exc
    return serialize_classroom(_owned_classroom(classroom.id, teacher_id), include_students=True)


def remove_student(class_id: int, student_id: int, teacher_id: int) -> dict:
    classroom = _owned_classroom(class_id, teacher_id)
    link = db.session.scalar(
        db.select(TeachingClassStudent).where(
            TeachingClassStudent.class_id == classroom.id,
            TeachingClassStudent.student_id == student_id,
        )
    )
    if link is None:
        raise ClassNotFound("班级中没有该学生")
    db.session.delete(link)
    db.session.commit()
    return serialize_classroom(_owned_classroom(classroom.id, teacher_id), include_students=True)


def assign_course(class_id: int, course_id: int, teacher_id: int) -> dict:
    classroom = _owned_classroom(class_id, teacher_id)
    course = db.session.get(Course, course_id)
    if course is None:
        raise ClassNotFound("课程不存在")
    if course.teacher_id != teacher_id:
        raise ClassPermissionDenied("只能关联自己负责的课程")
    existing = db.session.scalar(
        db.select(TeachingClassCourse).where(
            TeachingClassCourse.class_id == classroom.id,
            TeachingClassCourse.course_id == course.id,
        )
    )
    if existing is not None:
        raise ClassConflict("该课程已经关联到当前班级")

    db.session.add(TeachingClassCourse(class_id=classroom.id, course_id=course.id))
    _enroll_class_students(classroom, course.id)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ClassConflict("该课程已经关联到当前班级") from exc
    return serialize_classroom(_owned_classroom(classroom.id, teacher_id), include_students=True)


def unassign_course(class_id: int, course_id: int, teacher_id: int) -> dict:
    classroom = _owned_classroom(class_id, teacher_id)
    link = db.session.scalar(
        db.select(TeachingClassCourse).where(
            TeachingClassCourse.class_id == classroom.id,
            TeachingClassCourse.course_id == course_id,
        )
    )
    if link is None:
        raise ClassNotFound("班级尚未关联该课程")
    db.session.delete(link)
    db.session.commit()
    return serialize_classroom(_owned_classroom(classroom.id, teacher_id), include_students=True)


def serialize_classroom(
    classroom: TeachingClass,
    include_students: bool = False,
    viewer_student_id: int | None = None,
) -> dict:
    links = sorted(
        classroom.student_links,
        key=lambda item: (
            item.student.student_no or "",
            item.student.real_name,
            item.student_id,
        ),
    )
    payload = {
        "id": classroom.id,
        "name": classroom.name,
        "description": classroom.description,
        "teacher_id": classroom.teacher_id,
        "teacher_name": classroom.teacher.real_name,
        "teacher_no": classroom.teacher.teacher_no,
        "member_count": len(links),
        "created_at": iso_utc(classroom.created_at),
        "updated_at": iso_utc(classroom.updated_at),
    }
    course_links = sorted(
        classroom.course_links,
        key=lambda item: (item.assigned_at, item.id),
        reverse=True,
    )
    if viewer_student_id is not None:
        course_links = [
            link for link in course_links if link.course.status == CourseStatus.PUBLISHED.value
        ]
    payload["course_count"] = len(course_links)
    payload["courses"] = [
        {
            "id": link.course.id,
            "name": link.course.name,
            "description": link.course.description,
            "category_name": link.course.category.name if link.course.category else None,
            "status": link.course.status,
            "cover_url": f"/media/{link.course.cover}" if link.course.cover else None,
            "assigned_at": iso_utc(link.assigned_at),
        }
        for link in course_links
    ]
    if include_students:
        payload["students"] = [
            {
                "id": link.student.id,
                "username": link.student.username,
                "real_name": link.student.real_name,
                "student_no": link.student.student_no,
                "email": link.student.email,
                "phone": link.student.phone,
                "status": bool(link.student.status),
                "joined_at": iso_utc(link.joined_at),
            }
            for link in links
        ]
    elif viewer_student_id is not None:
        viewer_link = next(
            (link for link in links if link.student_id == viewer_student_id),
            None,
        )
        payload["joined_at"] = iso_utc(viewer_link.joined_at) if viewer_link else None
    return payload


def _owned_classroom(class_id: int, teacher_id: int) -> TeachingClass:
    classroom = db.session.scalar(
        db.select(TeachingClass)
        .options(
            selectinload(TeachingClass.teacher),
            selectinload(TeachingClass.student_links).selectinload(TeachingClassStudent.student),
            selectinload(TeachingClass.course_links)
            .selectinload(TeachingClassCourse.course)
            .selectinload(Course.category),
        )
        .where(TeachingClass.id == class_id)
    )
    if classroom is None:
        raise ClassNotFound("班级不存在")
    if classroom.teacher_id != teacher_id:
        raise ClassPermissionDenied("不能管理其他教师的班级")
    return classroom


def _ensure_unique_name(teacher_id: int, name: str, exclude_id: int | None = None) -> None:
    statement = db.select(TeachingClass.id).where(
        TeachingClass.teacher_id == teacher_id,
        TeachingClass.name == name,
    )
    if exclude_id is not None:
        statement = statement.where(TeachingClass.id != exclude_id)
    if db.session.scalar(statement) is not None:
        raise ClassConflict("你已经创建过同名班级")


def _enroll_class_students(classroom: TeachingClass, course_id: int) -> None:
    student_ids = [link.student_id for link in classroom.student_links]
    if not student_ids:
        return
    existing = {
        link.student_id: link
        for link in db.session.scalars(
            db.select(CourseStudent).where(
                CourseStudent.course_id == course_id,
                CourseStudent.student_id.in_(student_ids),
            )
        ).all()
    }
    now = utc_now()
    for student_id in student_ids:
        link = existing.get(student_id)
        if link is None:
            db.session.add(CourseStudent(course_id=course_id, student_id=student_id))
        elif not link.status:
            link.status = True
            link.join_time = now


def _enroll_student_in_class_courses(classroom: TeachingClass, student_id: int) -> None:
    course_ids = [link.course_id for link in classroom.course_links]
    if not course_ids:
        return
    existing = {
        link.course_id: link
        for link in db.session.scalars(
            db.select(CourseStudent).where(
                CourseStudent.student_id == student_id,
                CourseStudent.course_id.in_(course_ids),
            )
        ).all()
    }
    now = utc_now()
    for course_id in course_ids:
        link = existing.get(course_id)
        if link is None:
            db.session.add(CourseStudent(course_id=course_id, student_id=student_id))
        elif not link.status:
            link.status = True
            link.join_time = now
