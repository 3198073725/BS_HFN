from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from werkzeug.security import generate_password_hash

from app.constants import CourseStatus, UserRole
from app.extensions import db
from app.models import Course, CourseCategory, CourseStudent, Homework, User


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def create_user(username, role, number):
    user = User(
        username=username,
        password_hash=generate_password_hash("Password123!"),
        real_name=username,
        role=role,
        **{("teacher_no" if role == UserRole.TEACHER.value else "student_no"): number},
    )
    db.session.add(user)
    db.session.flush()
    return user


def login(client, username):
    response = client.post(
        "/api/auth/login",
        json={"account": username, "password": "Password123!"},
    )
    assert response.status_code == 200
    return response.get_json()["data"]["access_token"]


def create_context(app):
    with app.app_context():
        teacher = create_user("homework_teacher", UserRole.TEACHER.value, "HT001")
        other_teacher = create_user("homework_other_teacher", UserRole.TEACHER.value, "HT002")
        student = create_user("homework_student", UserRole.STUDENT.value, "HS001")
        other_student = create_user("homework_other_student", UserRole.STUDENT.value, "HS002")
        category = CourseCategory(name="作业测试")
        db.session.add(category)
        db.session.flush()
        course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="作业测试课程",
            status=CourseStatus.PUBLISHED.value,
        )
        db.session.add(course)
        db.session.flush()
        db.session.add(CourseStudent(course_id=course.id, student_id=student.id, status=True))
        db.session.commit()
        return {
            "course_id": course.id,
            "teacher": teacher.username,
            "other_teacher": other_teacher.username,
            "student": student.username,
            "other_student": other_student.username,
        }


def test_homework_publish_submit_grade_and_resubmit(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    other_teacher = login(client, context["other_teacher"])
    student = login(client, context["student"])
    other_student = login(client, context["other_student"])
    deadline = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    invalid = client.post(
        "/api/homeworks",
        headers=bearer(teacher),
        json={"course_id": context["course_id"], "title": "", "description": "说明"},
    )
    assert invalid.status_code == 400

    created = client.post(
        "/api/homeworks",
        headers=bearer(teacher),
        json={
            "course_id": context["course_id"],
            "title": "第一份作业",
            "description": "完成本章知识总结。",
            "deadline": deadline,
            "total_score": 100,
        },
    )
    assert created.status_code == 201
    homework_id = created.get_json()["data"]["id"]
    assert created.get_json()["data"]["status"] == "DRAFT"
    assert client.post(
        f"/api/homeworks/{homework_id}/attachment",
        headers=bearer(teacher),
        data={"attachment": (BytesIO(b"unsafe"), "payload.exe")},
        content_type="multipart/form-data",
    ).status_code == 400
    attached = client.post(
        f"/api/homeworks/{homework_id}/attachment",
        headers=bearer(teacher),
        data={"attachment": (BytesIO(b"teacher attachment"), "requirements.pdf")},
        content_type="multipart/form-data",
    )
    assert attached.status_code == 200
    attachment_path = attached.get_json()["data"]["attachment"]
    assert attachment_path.startswith(f"homework/{homework_id}/teacher/")
    with app.app_context():
        assert (Path(app.config["MEDIA_ROOT"]) / attachment_path).is_file()
    assert client.get("/api/homeworks", headers=bearer(student)).get_json()["data"] == []
    assert client.get(f"/api/homeworks/{homework_id}", headers=bearer(student)).status_code == 404
    assert client.put(
        f"/api/homeworks/{homework_id}",
        headers=bearer(other_teacher),
        json={"title": "越权修改"},
    ).status_code == 403

    updated = client.put(
        f"/api/homeworks/{homework_id}",
        headers=bearer(teacher),
        json={"title": "第一份阶段作业"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["title"] == "第一份阶段作业"

    published = client.post(
        f"/api/homeworks/{homework_id}/publish", headers=bearer(teacher)
    )
    assert published.status_code == 200
    assert published.get_json()["data"]["status"] == "PUBLISHED"
    assert client.put(
        f"/api/homeworks/{homework_id}",
        headers=bearer(teacher),
        json={"title": "发布后不能修改"},
    ).status_code == 409
    assert client.post(
        f"/api/homeworks/{homework_id}/attachment",
        headers=bearer(teacher),
        data={"attachment": (BytesIO(b"late"), "late.txt")},
        content_type="multipart/form-data",
    ).status_code == 409

    student_list = client.get("/api/homeworks", headers=bearer(student))
    assert student_list.status_code == 200
    assert student_list.get_json()["data"][0]["submission"] is None
    assert client.put(
        f"/api/homeworks/{homework_id}/submission",
        headers=bearer(other_student),
        json={"content": "未加入课程"},
    ).status_code == 403

    first = client.put(
        f"/api/homeworks/{homework_id}/submission",
        headers=bearer(student),
        json={"content": "第一次提交内容"},
    )
    assert first.status_code == 200
    submission_id = first.get_json()["data"]["id"]
    second = client.put(
        f"/api/homeworks/{homework_id}/submission",
        headers=bearer(student),
        json={"content": "修订后的提交内容"},
    )
    assert second.status_code == 200
    assert second.get_json()["data"]["id"] == submission_id
    assert second.get_json()["data"]["content"] == "修订后的提交内容"
    student_attachment = client.post(
        f"/api/homeworks/{homework_id}/submission/attachment",
        headers=bearer(student),
        data={"attachment": (BytesIO(b"student attachment"), "answer.docx")},
        content_type="multipart/form-data",
    )
    assert student_attachment.status_code == 200
    assert student_attachment.get_json()["data"]["attachment"].startswith(
        f"homework/{homework_id}/"
    )

    assert client.get(
        f"/api/homeworks/{homework_id}/submissions",
        headers=bearer(other_teacher),
    ).status_code == 403
    submissions = client.get(
        f"/api/homeworks/{homework_id}/submissions", headers=bearer(teacher)
    )
    assert submissions.status_code == 200
    assert len(submissions.get_json()["data"]) == 1
    assert client.put(
        f"/api/homeworks/submissions/{submission_id}/grade",
        headers=bearer(teacher),
        json={"score": 101},
    ).status_code == 409

    graded = client.put(
        f"/api/homeworks/submissions/{submission_id}/grade",
        headers=bearer(teacher),
        json={"score": 92.5, "teacher_comment": "结构清晰，继续保持。"},
    )
    assert graded.status_code == 200
    assert graded.get_json()["data"]["status"] == "GRADED"
    assert graded.get_json()["data"]["score"] == 92.5

    resubmitted = client.put(
        f"/api/homeworks/{homework_id}/submission",
        headers=bearer(student),
        json={"content": "根据评语再次提交"},
    )
    assert resubmitted.get_json()["data"]["status"] == "SUBMITTED"
    assert resubmitted.get_json()["data"]["score"] is None
    assert resubmitted.get_json()["data"]["teacher_comment"] is None

    closed = client.post(f"/api/homeworks/{homework_id}/close", headers=bearer(teacher))
    assert closed.status_code == 200
    assert closed.get_json()["data"]["status"] == "CLOSED"
    assert client.get(f"/api/homeworks/{homework_id}", headers=bearer(student)).status_code == 200
    assert client.put(
        f"/api/homeworks/{homework_id}/submission",
        headers=bearer(student),
        json={"content": "关闭后提交"},
    ).status_code == 409


def test_homework_past_deadline_cannot_publish_or_submit(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    student = login(client, context["student"])
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    created = client.post(
        "/api/homeworks",
        headers=bearer(teacher),
        json={
            "course_id": context["course_id"],
            "title": "过期作业",
            "description": "不应发布",
            "deadline": past,
        },
    )
    assert created.status_code == 201
    homework_id = created.get_json()["data"]["id"]
    assert client.post(
        f"/api/homeworks/{homework_id}/publish", headers=bearer(teacher)
    ).status_code == 409

    with app.app_context():
        homework = db.session.get(Homework, homework_id)
        homework.status = "PUBLISHED"
        db.session.commit()
    assert client.put(
        f"/api/homeworks/{homework_id}/submission",
        headers=bearer(student),
        json={"content": "已过截止时间"},
    ).status_code == 409
