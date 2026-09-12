from werkzeug.security import generate_password_hash

from app.constants import UserRole
from app.extensions import db
from app.models import User


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
