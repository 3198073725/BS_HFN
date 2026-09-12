from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app.constants import CourseStatus, UserRole
from app.extensions import db
from app.models import Course, CourseCategory, CourseStudent, User


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
        teacher = create_user("exam_teacher", UserRole.TEACHER.value, "ET001")
        other_teacher = create_user("exam_other_teacher", UserRole.TEACHER.value, "ET002")
        student = create_user("exam_student", UserRole.STUDENT.value, "ES001")
        other_student = create_user("exam_other_student", UserRole.STUDENT.value, "ES002")
        category = CourseCategory(name="测验测试")
        db.session.add(category)
        db.session.flush()
        course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="测验测试课程",
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


def create_exam(client, token, course_id, total_score=100, **extra):
    payload = {
        "course_id": course_id,
        "title": "第一章随堂测验",
        "description": "请选择正确答案。",
        "total_score": total_score,
        "time_limit_minutes": 30,
    }
    payload.update(extra)
    response = client.post("/api/exams", headers=bearer(token), json=payload)
    assert response.status_code == 201
    return response.get_json()["data"]


def test_exam_question_publish_take_and_auto_score(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    other_teacher = login(client, context["other_teacher"])
    student = login(client, context["student"])
    other_student = login(client, context["other_student"])
    exam = create_exam(client, teacher, context["course_id"])
    exam_id = exam["id"]

    assert client.post(f"/api/exams/{exam_id}/publish", headers=bearer(teacher)).status_code == 409
    single = client.post(
        f"/api/exams/{exam_id}/questions",
        headers=bearer(teacher),
        json={
            "question_type": "SINGLE",
            "content": "HTTP 的默认明文端口是？",
            "options": {"A": "80", "B": "443", "C": "22", "D": "3306"},
            "correct_answer": "A",
            "score": 60,
            "sort_order": 1,
        },
    )
    assert single.status_code == 201
    single_id = single.get_json()["data"]["id"]
    judge = client.post(
        f"/api/exams/{exam_id}/questions",
        headers=bearer(teacher),
        json={
            "question_type": "JUDGE",
            "content": "HTTPS 默认使用加密传输。",
            "correct_answer": "TRUE",
            "score": 40,
            "sort_order": 2,
        },
    )
    assert judge.status_code == 201
    judge_id = judge.get_json()["data"]["id"]
    assert client.put(
        f"/api/exams/questions/{single_id}",
        headers=bearer(other_teacher),
        json={
            "question_type": "SINGLE",
            "content": "越权编辑",
            "options": {"A": "1", "B": "2"},
            "correct_answer": "A",
            "score": 60,
        },
    ).status_code == 403

    published = client.post(f"/api/exams/{exam_id}/publish", headers=bearer(teacher))
    assert published.status_code == 200
    assert published.get_json()["data"]["status"] == "PUBLISHED"
    assert client.delete(
        f"/api/exams/questions/{judge_id}", headers=bearer(teacher)
    ).status_code == 409

    before = client.get(f"/api/exams/{exam_id}", headers=bearer(student))
    assert before.status_code == 200
    assert "correct_answer" not in before.get_json()["data"]["questions"][0]
    assert client.post(f"/api/exams/{exam_id}/start", headers=bearer(other_student)).status_code == 403

    started = client.post(f"/api/exams/{exam_id}/start", headers=bearer(student))
    assert started.status_code == 201
    record_id = started.get_json()["data"]["id"]
    assert started.get_json()["data"]["status"] == "DOING"
    repeated_start = client.post(f"/api/exams/{exam_id}/start", headers=bearer(student))
    assert repeated_start.status_code == 201
    assert repeated_start.get_json()["data"]["id"] == record_id

    invalid = client.post(
        f"/api/exams/{exam_id}/submit",
        headers=bearer(student),
        json={"answers": [{"question_id": 999999, "answer": "A"}]},
    )
    assert invalid.status_code == 409
    submitted = client.post(
        f"/api/exams/{exam_id}/submit",
        headers=bearer(student),
        json={
            "answers": [
                {"question_id": single_id, "answer": "a"},
                {"question_id": judge_id, "answer": "FALSE"},
            ]
        },
    )
    assert submitted.status_code == 200
    result = submitted.get_json()["data"]
    assert result["status"] == "SUBMITTED"
    assert result["score"] == 60.0
    assert result["correct_count"] == 1
    assert result["wrong_count"] == 1
    assert result["answers"][0]["question"]["correct_answer"] == "A"
    assert result["answers"][1]["is_correct"] is False
    assert client.post(
        f"/api/exams/{exam_id}/submit",
        headers=bearer(student),
        json={"answers": []},
    ).status_code == 409

    after = client.get(f"/api/exams/{exam_id}", headers=bearer(student)).get_json()["data"]
    assert after["record"]["score"] == 60.0
    assert after["questions"][0]["correct_answer"] == "A"
    teacher_records = client.get(f"/api/exams/{exam_id}/records", headers=bearer(teacher))
    assert teacher_records.status_code == 200
    assert teacher_records.get_json()["data"][0]["student_name"] == context["student"]
    assert client.get(f"/api/exams/records/{record_id}", headers=bearer(other_student)).status_code == 403

    closed = client.post(f"/api/exams/{exam_id}/close", headers=bearer(teacher))
    assert closed.status_code == 200
    assert client.get(f"/api/exams/{exam_id}", headers=bearer(student)).status_code == 200


def test_exam_score_sum_and_time_window_validation(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    student = login(client, context["student"])
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    later = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    exam = create_exam(
        client,
        teacher,
        context["course_id"],
        total_score=100,
        start_time=future,
        end_time=later,
    )
    exam_id = exam["id"]
    question = client.post(
        f"/api/exams/{exam_id}/questions",
        headers=bearer(teacher),
        json={
            "question_type": "JUDGE",
            "content": "分值合计测试",
            "correct_answer": "TRUE",
            "score": 90,
        },
    )
    assert question.status_code == 201
    assert client.post(f"/api/exams/{exam_id}/publish", headers=bearer(teacher)).status_code == 409
    question_id = question.get_json()["data"]["id"]
    assert client.put(
        f"/api/exams/questions/{question_id}",
        headers=bearer(teacher),
        json={
            "question_type": "JUDGE",
            "content": "分值合计测试",
            "correct_answer": "TRUE",
            "score": 100,
        },
    ).status_code == 200
    assert client.post(f"/api/exams/{exam_id}/publish", headers=bearer(teacher)).status_code == 200
    assert client.post(f"/api/exams/{exam_id}/start", headers=bearer(student)).status_code == 409

    invalid_window = client.put(
        f"/api/exams/{exam_id}",
        headers=bearer(teacher),
        json={"start_time": later, "end_time": future},
    )
    assert invalid_window.status_code == 400
