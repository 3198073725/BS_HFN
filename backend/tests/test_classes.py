from werkzeug.security import generate_password_hash

from app.constants import CourseStatus, UserRole
from app.extensions import db
from app.models import Course, CourseCategory, CourseStudent, User


PASSWORD = "Password123!"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def create_user(username: str, role: str, number: str | None = None, status: bool = True):
    values = {
        "username": username,
        "password_hash": generate_password_hash(PASSWORD),
        "real_name": username,
        "role": role,
        "status": status,
    }
    if role == UserRole.TEACHER.value:
        values["teacher_no"] = number
    elif role == UserRole.STUDENT.value:
        values["student_no"] = number
    user = User(**values)
    db.session.add(user)
    db.session.flush()
    return user


def login(client, username: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"account": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.get_json()["data"]["access_token"]


def create_context(app):
    with app.app_context():
        teacher = create_user("class_teacher", UserRole.TEACHER.value, "CT001")
        other_teacher = create_user("other_class_teacher", UserRole.TEACHER.value, "CT002")
        student = create_user("class_student", UserRole.STUDENT.value, "CS001")
        other_student = create_user("other_class_student", UserRole.STUDENT.value, "CS002")
        disabled_student = create_user(
            "disabled_class_student",
            UserRole.STUDENT.value,
            "CS003",
            status=False,
        )
        db.session.commit()
        return {
            "teacher": teacher.username,
            "teacher_id": teacher.id,
            "other_teacher": other_teacher.username,
            "student": student.username,
            "student_id": student.id,
            "other_student": other_student.username,
            "disabled_student": disabled_student.username,
        }


def test_teacher_classroom_and_student_roster_lifecycle(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    other_teacher = login(client, context["other_teacher"])
    student = login(client, context["student"])
    other_student = login(client, context["other_student"])

    forbidden_create = client.post(
        "/api/classes",
        headers=bearer(student),
        json={"name": "越权班级"},
    )
    assert forbidden_create.status_code == 403

    created = client.post(
        "/api/classes",
        headers=bearer(teacher),
        json={"name": "软件工程一班", "description": "2026 秋季辅导班"},
    )
    assert created.status_code == 201
    classroom = created.get_json()["data"]
    class_id = classroom["id"]
    assert classroom["member_count"] == 0
    assert classroom["students"] == []

    duplicate_name = client.post(
        "/api/classes",
        headers=bearer(teacher),
        json={"name": "软件工程一班"},
    )
    assert duplicate_name.status_code == 409

    other_teacher_edit = client.put(
        f"/api/classes/{class_id}",
        headers=bearer(other_teacher),
        json={"name": "不应成功"},
    )
    assert other_teacher_edit.status_code == 403

    added = client.post(
        f"/api/classes/{class_id}/students",
        headers=bearer(teacher),
        json={"account": "CS001"},
    )
    assert added.status_code == 201
    added_classroom = added.get_json()["data"]
    assert added_classroom["member_count"] == 1
    assert added_classroom["students"][0]["username"] == context["student"]

    duplicate_student = client.post(
        f"/api/classes/{class_id}/students",
        headers=bearer(teacher),
        json={"account": context["student"]},
    )
    assert duplicate_student.status_code == 409

    teacher_as_student = client.post(
        f"/api/classes/{class_id}/students",
        headers=bearer(teacher),
        json={"account": context["other_teacher"]},
    )
    assert teacher_as_student.status_code == 409

    teacher_classes = client.get("/api/classes", headers=bearer(teacher))
    assert teacher_classes.status_code == 200
    assert teacher_classes.get_json()["data"][0]["students"][0]["student_no"] == "CS001"

    student_classes = client.get("/api/classes", headers=bearer(student))
    assert student_classes.status_code == 200
    student_classroom = student_classes.get_json()["data"][0]
    assert student_classroom["teacher_name"] == context["teacher"]
    assert student_classroom["joined_at"] is not None
    assert "students" not in student_classroom
    assert client.get("/api/classes", headers=bearer(other_student)).get_json()["data"] == []

    updated = client.put(
        f"/api/classes/{class_id}",
        headers=bearer(teacher),
        json={"name": "软件工程重点班", "description": "更新后的说明"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["name"] == "软件工程重点班"

    removed = client.delete(
        f"/api/classes/{class_id}/students/{context['student_id']}",
        headers=bearer(teacher),
    )
    assert removed.status_code == 200
    assert removed.get_json()["data"]["member_count"] == 0
    assert client.get("/api/classes", headers=bearer(student)).get_json()["data"] == []

    assert client.delete(
        f"/api/classes/{class_id}",
        headers=bearer(other_teacher),
    ).status_code == 403
    assert client.delete(
        f"/api/classes/{class_id}",
        headers=bearer(teacher),
    ).status_code == 200
    assert client.get("/api/classes", headers=bearer(teacher)).get_json()["data"] == []


def test_classroom_input_and_student_status_validation(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])

    assert client.post(
        "/api/classes",
        headers=bearer(teacher),
        json={"name": ""},
    ).status_code == 400
    assert client.post(
        "/api/classes",
        headers=bearer(teacher),
        json={"name": "有效班级", "description": "x" * 501},
    ).status_code == 400

    created = client.post(
        "/api/classes",
        headers=bearer(teacher),
        json={"name": "有效班级"},
    )
    class_id = created.get_json()["data"]["id"]

    assert client.put(
        f"/api/classes/{class_id}",
        headers=bearer(teacher),
        json={},
    ).status_code == 400
    assert client.post(
        f"/api/classes/{class_id}/students",
        headers=bearer(teacher),
        json={"account": ""},
    ).status_code == 400
    assert client.post(
        f"/api/classes/{class_id}/students",
        headers=bearer(teacher),
        json={"account": "missing_student"},
    ).status_code == 404
    disabled = client.post(
        f"/api/classes/{class_id}/students",
        headers=bearer(teacher),
        json={"account": context["disabled_student"]},
    )
    assert disabled.status_code == 409
    assert disabled.get_json()["message"] == "该学生账号已被禁用"


def test_student_can_join_a_linked_class_from_published_course(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    student = login(client, context["student"])

    with app.app_context():
        category = CourseCategory(name="公开加入班级分类")
        db.session.add(category)
        db.session.flush()
        course = Course(
            teacher_id=context["teacher_id"],
            category_id=category.id,
            name="公开班级课程",
            status=CourseStatus.PUBLISHED.value,
        )
        db.session.add(course)
        db.session.commit()
        course_id = course.id

    classroom = client.post(
        "/api/classes",
        headers=bearer(teacher),
        json={"name": "可加入班级"},
    ).get_json()["data"]
    assert client.post(
        f"/api/classes/{classroom['id']}/courses",
        headers=bearer(teacher),
        json={"course_id": course_id},
    ).status_code == 201

    options = client.get(f"/api/courses/{course_id}/classes", headers=bearer(student))
    assert options.status_code == 200
    assert options.get_json()["data"][0]["joined"] is False
    joined = client.post(
        f"/api/courses/{course_id}/classes/{classroom['id']}/join",
        headers=bearer(student),
    )
    assert joined.status_code == 201
    assert joined.get_json()["data"]["name"] == "可加入班级"
    assert client.post(
        f"/api/courses/{course_id}/classes/{classroom['id']}/join",
        headers=bearer(student),
    ).status_code == 409
    with app.app_context():
        assert db.session.scalar(
            db.select(CourseStudent).where(
                CourseStudent.course_id == course_id,
                CourseStudent.student_id == context["student_id"],
                CourseStudent.status.is_(True),
            )
        ) is not None


def test_classroom_course_assignment_enrolls_existing_and_future_students(app, client):
    context = create_context(app)
    with app.app_context():
        category = CourseCategory(name="班级课程分类")
        db.session.add(category)
        db.session.flush()
        course = Course(
            teacher_id=context["teacher_id"],
            category_id=category.id,
            name="班级同步课程",
            status=CourseStatus.PUBLISHED.value,
        )
        draft_course = Course(
            teacher_id=context["teacher_id"],
            category_id=category.id,
            name="待发布班级课程",
            status=CourseStatus.DRAFT.value,
        )
        other_course = Course(
            teacher_id=db.session.scalar(
                db.select(User.id).where(User.username == context["other_teacher"])
            ),
            category_id=category.id,
            name="其他教师课程",
            status=CourseStatus.PUBLISHED.value,
        )
        db.session.add_all([course, draft_course, other_course])
        db.session.commit()
        course_id = course.id
        draft_course_id = draft_course.id
        other_course_id = other_course.id

    teacher = login(client, context["teacher"])
    other_teacher = login(client, context["other_teacher"])
    student = login(client, context["student"])

    options = client.get("/api/classes/course-options", headers=bearer(teacher))
    assert options.status_code == 200
    assert {item["id"] for item in options.get_json()["data"]} == {
        course_id,
        draft_course_id,
    }
    assert client.get(
        "/api/classes/course-options",
        headers=bearer(student),
    ).status_code == 403

    created = client.post(
        "/api/classes",
        headers=bearer(teacher),
        json={"name": "课程同步班"},
    )
    class_id = created.get_json()["data"]["id"]
    assert client.post(
        f"/api/classes/{class_id}/students",
        headers=bearer(teacher),
        json={"account": context["student"]},
    ).status_code == 201

    assigned = client.post(
        f"/api/classes/{class_id}/courses",
        headers=bearer(teacher),
        json={"course_id": course_id},
    )
    assert assigned.status_code == 201
    classroom = assigned.get_json()["data"]
    assert classroom["course_count"] == 1
    assert classroom["courses"][0]["name"] == "班级同步课程"
    with app.app_context():
        first_enrollment = db.session.scalar(
            db.select(CourseStudent).where(
                CourseStudent.course_id == course_id,
                CourseStudent.student_id == context["student_id"],
            )
        )
        assert first_enrollment is not None
        assert first_enrollment.status is True

    assert client.post(
        f"/api/classes/{class_id}/courses",
        headers=bearer(teacher),
        json={"course_id": course_id},
    ).status_code == 409
    assert client.post(
        f"/api/classes/{class_id}/courses",
        headers=bearer(other_teacher),
        json={"course_id": course_id},
    ).status_code == 403
    assert client.post(
        f"/api/classes/{class_id}/courses",
        headers=bearer(teacher),
        json={"course_id": other_course_id},
    ).status_code == 403
    assert client.post(
        f"/api/classes/{class_id}/courses",
        headers=bearer(teacher),
        json={"course_id": "invalid"},
    ).status_code == 400

    assert client.post(
        f"/api/classes/{class_id}/courses",
        headers=bearer(teacher),
        json={"course_id": draft_course_id},
    ).status_code == 201
    added_future_student = client.post(
        f"/api/classes/{class_id}/students",
        headers=bearer(teacher),
        json={"account": context["other_student"]},
    )
    assert added_future_student.status_code == 201
    with app.app_context():
        second_student_id = db.session.scalar(
            db.select(User.id).where(User.username == context["other_student"])
        )
        synced_course_ids = set(
            db.session.scalars(
                db.select(CourseStudent.course_id).where(
                    CourseStudent.student_id == second_student_id,
                    CourseStudent.status.is_(True),
                )
            ).all()
        )
        assert synced_course_ids == {course_id, draft_course_id}

    student_classroom = client.get(
        "/api/classes",
        headers=bearer(student),
    ).get_json()["data"][0]
    assert student_classroom["course_count"] == 1
    assert [item["id"] for item in student_classroom["courses"]] == [course_id]

    removed = client.delete(
        f"/api/classes/{class_id}/courses/{course_id}",
        headers=bearer(teacher),
    )
    assert removed.status_code == 200
    assert removed.get_json()["data"]["course_count"] == 1
    with app.app_context():
        preserved_enrollment = db.session.scalar(
            db.select(CourseStudent).where(
                CourseStudent.course_id == course_id,
                CourseStudent.student_id == context["student_id"],
            )
        )
        assert preserved_enrollment.status is True
    assert client.delete(
        f"/api/classes/{class_id}/courses/{course_id}",
        headers=bearer(teacher),
    ).status_code == 404
