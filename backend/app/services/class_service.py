from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.constants import ClassJoinRequestStatus, CourseStatus, UserRole
from app.datetime_utils import iso_utc, utc_now
from app.extensions import db
from app.models import (
    Course,
    CourseStudent,
    TeachingClass,
    TeachingClassCourse,
    TeachingClassJoinRequest,
    TeachingClassStudent,
    User,
)
from app.services.notification_service import queue_notification


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


def list_course_class_options(course_id: int, student_id: int) -> list[dict]:
    course = db.session.get(Course, course_id)
    if course is None or course.status != CourseStatus.PUBLISHED.value:
        raise ClassNotFound("课程不存在或尚未发布")
    classrooms = db.session.scalars(
        db.select(TeachingClass)
        .options(
            selectinload(TeachingClass.teacher),
            selectinload(TeachingClass.student_links),
        )
        .join(TeachingClassCourse, TeachingClassCourse.class_id == TeachingClass.id)
        .where(TeachingClassCourse.course_id == course_id)
        .order_by(TeachingClass.created_at.desc(), TeachingClass.id.desc())
    ).all()
    request_by_class_id = {
        item.class_id: item
        for item in db.session.scalars(
            db.select(TeachingClassJoinRequest).where(
                TeachingClassJoinRequest.student_id == student_id,
                TeachingClassJoinRequest.class_id.in_([item.id for item in classrooms]),
            )
        ).all()
    } if classrooms else {}
    return [
        {
            "id": classroom.id,
            "name": classroom.name,
            "description": classroom.description,
            "teacher_id": classroom.teacher_id,
            "teacher_name": classroom.teacher.real_name,
            "member_count": len(classroom.student_links),
            "joined": any(link.student_id == student_id for link in classroom.student_links),
            "request_status": (
                request_by_class_id[classroom.id].status
                if classroom.id in request_by_class_id
                else None
            ),
        }
        for classroom in classrooms
    ]


def request_course_class_join(course_id: int, class_id: int, student_id: int) -> dict:
    course = db.session.get(Course, course_id)
    if course is None or course.status != CourseStatus.PUBLISHED.value:
        raise ClassNotFound("课程不存在或尚未发布")
    classroom = db.session.scalar(
        db.select(TeachingClass)
        .options(
            selectinload(TeachingClass.teacher),
            selectinload(TeachingClass.student_links),
            selectinload(TeachingClass.course_links),
        )
        .join(TeachingClassCourse, TeachingClassCourse.class_id == TeachingClass.id)
        .where(
            TeachingClass.id == class_id,
            TeachingClassCourse.course_id == course_id,
        )
    )
    if classroom is None:
        raise ClassNotFound("该课程没有关联这个班级")
    if any(link.student_id == student_id for link in classroom.student_links):
        raise ClassConflict("你已经加入该班级")
    join_request = db.session.scalar(
        db.select(TeachingClassJoinRequest).where(
            TeachingClassJoinRequest.class_id == classroom.id,
            TeachingClassJoinRequest.student_id == student_id,
        )
    )
    if join_request is not None and join_request.status == ClassJoinRequestStatus.PENDING.value:
        raise ClassConflict("你已经提交过入班申请，请等待教师审批")
    now = utc_now()
    if join_request is None:
        join_request = TeachingClassJoinRequest(
            class_id=classroom.id,
            student_id=student_id,
            source_course_id=course.id,
            status=ClassJoinRequestStatus.PENDING.value,
        )
        db.session.add(join_request)
    else:
        join_request.source_course_id = course.id
        join_request.status = ClassJoinRequestStatus.PENDING.value
        join_request.reviewer_id = None
        join_request.reviewed_at = None
        join_request.created_at = now
    db.session.flush()
    student_name = db.session.scalar(db.select(User.real_name).where(User.id == student_id))
    queue_notification(
        classroom.teacher_id,
        "新的入班申请",
        f"{student_name}申请加入“{classroom.name}”，请在班级管理中审批。",
        category="CLASS",
        sender_id=student_id,
        link=f"/classes?join_request_id={join_request.id}",
    )
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ClassConflict("你已经提交过入班申请，请等待教师审批") from exc
    return {
        "id": join_request.id,
        "class_id": classroom.id,
        "class_name": classroom.name,
        "status": join_request.status,
        "requested_at": iso_utc(join_request.created_at),
    }


def list_teacher_class_join_requests(teacher_id: int) -> list[dict]:
    requests = db.session.scalars(
        db.select(TeachingClassJoinRequest)
        .options(
            selectinload(TeachingClassJoinRequest.classroom),
            selectinload(TeachingClassJoinRequest.student),
            selectinload(TeachingClassJoinRequest.source_course),
        )
        .join(TeachingClass, TeachingClass.id == TeachingClassJoinRequest.class_id)
        .where(
            TeachingClass.teacher_id == teacher_id,
            TeachingClassJoinRequest.status == ClassJoinRequestStatus.PENDING.value,
        )
        .order_by(TeachingClassJoinRequest.created_at.asc(), TeachingClassJoinRequest.id.asc())
    ).all()
    return [_serialize_join_request(item) for item in requests]


def review_class_join_request(
    request_id: int,
    teacher_id: int,
    action: str,
) -> dict:
    join_request = db.session.scalar(
        db.select(TeachingClassJoinRequest)
        .options(
            selectinload(TeachingClassJoinRequest.classroom)
            .selectinload(TeachingClass.course_links),
            selectinload(TeachingClassJoinRequest.student),
            selectinload(TeachingClassJoinRequest.source_course),
        )
        .where(TeachingClassJoinRequest.id == request_id)
    )
    if join_request is None:
        raise ClassNotFound("入班申请不存在")
    if join_request.classroom.teacher_id != teacher_id:
        raise ClassPermissionDenied("不能审批其他教师班级的申请")
    if join_request.status != ClassJoinRequestStatus.PENDING.value:
        raise ClassConflict("该入班申请已经处理")

    approved = action == ClassJoinRequestStatus.APPROVED.value
    if approved:
        if not join_request.student.status:
            raise ClassConflict("该学生账号已被禁用，不能加入班级")
        membership = db.session.scalar(
            db.select(TeachingClassStudent).where(
                TeachingClassStudent.class_id == join_request.class_id,
                TeachingClassStudent.student_id == join_request.student_id,
            )
        )
        if membership is None:
            db.session.add(
                TeachingClassStudent(
                    class_id=join_request.class_id,
                    student_id=join_request.student_id,
                )
            )
            _enroll_student_in_class_courses(join_request.classroom, join_request.student_id)
    join_request.status = action
    join_request.reviewer_id = teacher_id
    join_request.reviewed_at = utc_now()
    queue_notification(
        join_request.student_id,
        "入班申请已通过" if approved else "入班申请未通过",
        (
            f"你已加入“{join_request.classroom.name}”，班级课程已同步到我的学习。"
            if approved
            else f"你加入“{join_request.classroom.name}”的申请未通过，可联系教师或重新申请。"
        ),
        category="CLASS",
        sender_id=teacher_id,
        link=(
            "/classes"
            if approved
            else (
                f"/courses/{join_request.source_course_id}"
                if join_request.source_course_id
                else "/courses"
            )
        ),
    )
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ClassConflict("该学生已经在班级中") from exc
    return _serialize_join_request(join_request)


def _serialize_join_request(join_request: TeachingClassJoinRequest) -> dict:
    return {
        "id": join_request.id,
        "class_id": join_request.class_id,
        "class_name": join_request.classroom.name,
        "student_id": join_request.student_id,
        "student_name": join_request.student.real_name,
        "student_no": join_request.student.student_no,
        "username": join_request.student.username,
        "source_course_id": join_request.source_course_id,
        "source_course_name": (
            join_request.source_course.name if join_request.source_course else None
        ),
        "status": join_request.status,
        "requested_at": iso_utc(join_request.created_at),
        "reviewed_at": iso_utc(join_request.reviewed_at),
    }


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
    pending_request = db.session.scalar(
        db.select(TeachingClassJoinRequest).where(
            TeachingClassJoinRequest.class_id == classroom.id,
            TeachingClassJoinRequest.student_id == student.id,
            TeachingClassJoinRequest.status == ClassJoinRequestStatus.PENDING.value,
        )
    )
    if pending_request is not None:
        pending_request.status = ClassJoinRequestStatus.APPROVED.value
        pending_request.reviewer_id = teacher_id
        pending_request.reviewed_at = utc_now()
        queue_notification(
            student.id,
            "入班申请已通过",
            f"你已加入“{classroom.name}”，班级课程已同步到我的学习。",
            category="CLASS",
            sender_id=teacher_id,
            link="/classes",
        )
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
        "teacher_avatar_url": (
            f"/media/{classroom.teacher.avatar}" if classroom.teacher.avatar else None
        ),
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
