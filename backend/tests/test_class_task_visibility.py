from io import BytesIO

from werkzeug.security import generate_password_hash

from app.constants import CourseStatus, UserRole
from app.extensions import db
from app.models import (
    Course,
    CourseCategory,
    CourseStudent,
    TeachingClass,
    TeachingClassCourse,
    TeachingClassJoinRequest,
    User,
)


PASSWORD = "Password123!"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, username):
    response = client.post(
        "/api/auth/login",
        json={"account": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.get_json()["data"]["access_token"]


def test_class_tasks_stay_hidden_until_teacher_approval(app, client):
    with app.app_context():
        teacher = User(
            username="class_task_teacher",
            password_hash=generate_password_hash(PASSWORD),
            real_name="班级任务教师",
            role=UserRole.TEACHER.value,
            teacher_no="CTV001",
        )
        student = User(
            username="class_task_student",
            password_hash=generate_password_hash(PASSWORD),
            real_name="待审批学生",
            role=UserRole.STUDENT.value,
            student_no="CSV001",
        )
        category = CourseCategory(name="班级任务权限")
        db.session.add_all([teacher, student, category])
        db.session.flush()
        course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="班级绑定课程",
            status=CourseStatus.PUBLISHED.value,
        )
        classroom = TeachingClass(teacher_id=teacher.id, name="审批后可见班")
        db.session.add_all([course, classroom])
        db.session.flush()
        db.session.add_all([
            CourseStudent(course_id=course.id, student_id=student.id, status=True),
            TeachingClassCourse(class_id=classroom.id, course_id=course.id),
            TeachingClassJoinRequest(
                class_id=classroom.id,
                student_id=student.id,
                source_course_id=course.id,
                status="PENDING",
            ),
        ])
        db.session.commit()
        context = {
            "teacher": teacher.username,
            "student": student.username,
            "course_id": course.id,
        }

    teacher_token = login(client, context["teacher"])
    student_token = login(client, context["student"])

    homework = client.post("/api/homeworks", headers=bearer(teacher_token), json={
        "course_id": context["course_id"],
        "title": "审批后作业",
        "description": "只有正式班级成员可见",
        "deadline": None,
        "total_score": 100,
    })
    assert homework.status_code == 201
    homework_data = homework.get_json()["data"]
    assert homework_data["deadline"] is None
    assert client.post(
        f"/api/homeworks/{homework_data['id']}/publish",
        headers=bearer(teacher_token),
    ).status_code == 200

    exam = client.post("/api/exams", headers=bearer(teacher_token), json={
        "exam_type": "ONLINE",
        "course_id": context["course_id"],
        "title": "审批后在线测验",
        "description": "系统内逐题作答",
        "total_score": 100,
        "time_limit_minutes": 30,
    })
    assert exam.status_code == 201
    exam_data = exam.get_json()["data"]
    attachment = client.post(
        f"/api/exams/{exam_data['id']}/attachment",
        headers=bearer(teacher_token),
        data={"attachment": (BytesIO(b"must not save"), "wrong.txt")},
        content_type="multipart/form-data",
    )
    assert attachment.status_code == 409
    assert "在线试题不使用试卷附件" in attachment.get_json()["message"]
    assert client.delete(
        f"/api/exams/{exam_data['id']}/attachment",
        headers=bearer(teacher_token),
    ).status_code == 409
    assert client.post(
        f"/api/exams/{exam_data['id']}/questions",
        headers=bearer(teacher_token),
        json={
            "question_type": "JUDGE",
            "content": "审批通过后可以看到本题。",
            "correct_answer": "TRUE",
            "score": 100,
            "sort_order": 1,
        },
    ).status_code == 201
    assert client.post(
        f"/api/exams/{exam_data['id']}/publish",
        headers=bearer(teacher_token),
    ).status_code == 200

    assert client.get("/api/homeworks", headers=bearer(student_token)).get_json()["data"] == []
    assert client.get("/api/exams", headers=bearer(student_token)).get_json()["data"] == []
    assert client.get(
        f"/api/homeworks/{homework_data['id']}", headers=bearer(student_token)
    ).status_code == 403
    assert client.get(
        f"/api/exams/{exam_data['id']}", headers=bearer(student_token)
    ).status_code == 403
    notifications = client.get(
        "/api/notifications", headers=bearer(student_token)
    ).get_json()["data"]["items"]
    assert not any(item["category"] in {"HOMEWORK", "EXAM"} for item in notifications)

    requests = client.get(
        "/api/classes/join-requests", headers=bearer(teacher_token)
    ).get_json()["data"]
    assert len(requests) == 1
    assert client.put(
        f"/api/classes/join-requests/{requests[0]['id']}",
        headers=bearer(teacher_token),
        json={"action": "APPROVED"},
    ).status_code == 200

    visible_homeworks = client.get(
        "/api/homeworks", headers=bearer(student_token)
    ).get_json()["data"]
    visible_exams = client.get(
        "/api/exams", headers=bearer(student_token)
    ).get_json()["data"]
    assert [item["id"] for item in visible_homeworks] == [homework_data["id"]]
    assert [item["id"] for item in visible_exams] == [exam_data["id"]]
