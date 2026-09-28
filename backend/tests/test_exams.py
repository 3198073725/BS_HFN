from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import pytest

from werkzeug.security import generate_password_hash

from app.constants import CourseStatus, UserRole
from app.extensions import db
from app.models import Course, CourseCategory, CourseStudent, Exam, ExamRecord, User


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


@pytest.mark.parametrize("exam_type", ["ONLINE", "ATTACHMENT"])
def test_closing_unlimited_exam_finalizes_saved_records(app, client, exam_type):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    student = login(client, context["student"])
    exam = create_exam(client, teacher, context["course_id"], exam_type=exam_type, time_limit_minutes=None)
    exam_id = exam["id"]
    if exam_type == "ONLINE":
        question = client.post(f"/api/exams/{exam_id}/questions", headers=bearer(teacher), json={
            "question_type": "JUDGE", "content": "判断题", "correct_answer": "TRUE", "score": 100,
        }).get_json()["data"]
    else:
        assert client.post(f"/api/exams/{exam_id}/attachment", headers=bearer(teacher),
                           data={"attachment": (BytesIO(b"paper"), "paper.txt")}).status_code == 200
    assert client.post(f"/api/exams/{exam_id}/publish", headers=bearer(teacher)).status_code == 200
    record = client.post(f"/api/exams/{exam_id}/start", headers=bearer(student)).get_json()["data"]
    if exam_type == "ONLINE":
        assert client.put(f"/api/exams/{exam_id}/answers", headers=bearer(student), json={
            "answers": [{"question_id": question["id"], "answer": "TRUE"}],
        }).status_code == 200
    else:
        assert client.put(f"/api/exams/{exam_id}/submission", headers=bearer(student),
                          json={"content": "已保存答案"}).status_code == 200
    closed = client.post(f"/api/exams/{exam_id}/close", headers=bearer(teacher))
    assert closed.status_code == 200
    assert closed.get_json()["data"]["submitted_count"] == 1
    result = client.get(f"/api/exams/records/{record['id']}", headers=bearer(student)).get_json()["data"]
    assert result["status"] == "SUBMITTED"
    assert result["submit_time"] and result["duration_seconds"] >= 0
    assert result["score"] == (100 if exam_type == "ONLINE" else None)
    if exam_type == "ATTACHMENT":
        assert result["content"] == "已保存答案"
        assert client.put(f"/api/exams/records/{record['id']}/grade", headers=bearer(teacher),
                          json={"score": 90}).status_code == 200
    assert client.post(f"/api/exams/{exam_id}/start", headers=bearer(student)).status_code == 409


def test_unauthorized_record_read_has_no_finalization_side_effect(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    student = login(client, context["student"])
    other_student = login(client, context["other_student"])
    other_teacher = login(client, context["other_teacher"])
    exam = create_exam(client, teacher, context["course_id"])
    exam_id = exam["id"]
    client.post(f"/api/exams/{exam_id}/questions", headers=bearer(teacher), json={
        "question_type": "JUDGE", "content": "判断题", "correct_answer": "TRUE", "score": 100,
    })
    client.post(f"/api/exams/{exam_id}/publish", headers=bearer(teacher))
    record_id = client.post(f"/api/exams/{exam_id}/start", headers=bearer(student)).get_json()["data"]["id"]
    with app.app_context():
        db.session.get(ExamRecord, record_id).started_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        db.session.commit()
    for token in (other_student, other_teacher):
        assert client.get(f"/api/exams/records/{record_id}", headers=bearer(token)).status_code == 403
        with app.app_context():
            assert db.session.get(ExamRecord, record_id).status == "DOING"
    assert client.get(f"/api/exams/records/{record_id}", headers=bearer(student)).get_json()["data"]["status"] == "SUBMITTED"


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


def test_exam_past_end_time_is_ended_without_teacher_closing(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    student = login(client, context["student"])
    end_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    exam = create_exam(
        client,
        teacher,
        context["course_id"],
        total_score=100,
        end_time=end_time,
        time_limit_minutes=None,
    )
    exam_id = exam["id"]
    assert client.post(
        f"/api/exams/{exam_id}/questions",
        headers=bearer(teacher),
        json={
            "question_type": "JUDGE",
            "content": "截止后不能开始",
            "correct_answer": "TRUE",
            "score": 100,
        },
    ).status_code == 201
    assert client.post(f"/api/exams/{exam_id}/publish", headers=bearer(teacher)).status_code == 200

    with app.app_context():
        stored = db.session.get(Exam, exam_id)
        stored.end_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.session.commit()

    student_item = client.get("/api/exams", headers=bearer(student)).get_json()["data"][0]
    assert student_item["status"] == "PUBLISHED"
    assert student_item["availability"] == "ENDED"
    assert student_item["is_expired"] is True
    teacher_item = client.get("/api/exams/manage", headers=bearer(teacher)).get_json()["data"][0]
    assert teacher_item["availability"] == "ENDED"
    assert client.post(f"/api/exams/{exam_id}/start", headers=bearer(student)).status_code == 409


def test_exam_draft_with_past_end_time_remains_draft(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    exam = create_exam(
        client,
        teacher,
        context["course_id"],
        end_time=past,
        time_limit_minutes=None,
    )
    assert exam["status"] == "DRAFT"
    assert exam["availability"] == "DRAFT"
    assert exam["is_expired"] is False
    teacher_item = client.get("/api/exams/manage", headers=bearer(teacher)).get_json()["data"][0]
    assert teacher_item["availability"] == "DRAFT"


def test_only_owner_can_delete_draft_exam_with_questions(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    other_teacher = login(client, context["other_teacher"])
    exam = create_exam(client, teacher, context["course_id"])
    exam_id = exam["id"]
    question = client.post(
        f"/api/exams/{exam_id}/questions",
        headers=bearer(teacher),
        json={
            "question_type": "JUDGE",
            "content": "待删除的草稿试题",
            "correct_answer": "TRUE",
            "score": 100,
        },
    )
    assert question.status_code == 201

    forbidden = client.delete(f"/api/exams/{exam_id}", headers=bearer(other_teacher))
    assert forbidden.status_code == 403
    deleted = client.delete(f"/api/exams/{exam_id}", headers=bearer(teacher))
    assert deleted.status_code == 200
    assert client.get(f"/api/exams/{exam_id}", headers=bearer(teacher)).status_code == 404


def test_exam_answers_are_saved_and_expired_record_uses_saved_draft(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    student = login(client, context["student"])
    exam = create_exam(client, teacher, context["course_id"], total_score=100, time_limit_minutes=30)
    question = client.post(
        f"/api/exams/{exam['id']}/questions",
        headers=bearer(teacher),
        json={
            "question_type": "SINGLE",
            "content": "自动保存测试",
            "options": {"A": "正确", "B": "错误"},
            "correct_answer": "A",
            "score": 100,
        },
    ).get_json()["data"]
    assert client.post(f"/api/exams/{exam['id']}/publish", headers=bearer(teacher)).status_code == 200
    started = client.post(f"/api/exams/{exam['id']}/start", headers=bearer(student)).get_json()["data"]
    saved = client.put(
        f"/api/exams/{exam['id']}/answers",
        headers=bearer(student),
        json={"answers": [{"question_id": question["id"], "answer": "A"}]},
    )
    assert saved.status_code == 200
    assert saved.get_json()["data"]["draft_answers"][0]["answer"] == "A"

    with app.app_context():
        record = db.session.get(ExamRecord, started["id"])
        record.started_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=31)
        db.session.commit()

    submitted = client.post(
        f"/api/exams/{exam['id']}/submit",
        headers=bearer(student),
        json={"answers": [{"question_id": question["id"], "answer": "B"}]},
    )
    assert submitted.status_code == 200
    assert submitted.get_json()["data"]["status"] == "SUBMITTED"
    assert submitted.get_json()["data"]["score"] == 100.0
    assert submitted.get_json()["data"]["duration_seconds"] == 1800
    assert client.put(
        f"/api/exams/{exam['id']}/answers",
        headers=bearer(student),
        json={"answers": [{"question_id": question["id"], "answer": "B"}]},
    ).status_code == 409


def test_exam_attachment_permissions_validation_and_lifecycle(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    other_teacher = login(client, context["other_teacher"])
    student = login(client, context["student"])
    outsider = login(client, context["other_student"])
    exam = create_exam(client, teacher, context["course_id"], exam_type="ATTACHMENT")
    endpoint = f"/api/exams/{exam['id']}/attachment"

    def upload(token=teacher, name="测验资料.txt", content=b"exam reference"):
        return client.post(endpoint, headers=bearer(token),
                           data={"attachment": (BytesIO(content), name)})

    assert client.get(endpoint).status_code == 401
    assert client.post(endpoint, headers=bearer(teacher)).status_code == 400
    assert upload(other_teacher).status_code == 403
    assert upload(student).status_code == 403
    assert upload(name="unsafe.html").status_code == 400
    assert upload(content=b"").status_code == 400
    app.config["EXAM_ATTACHMENT_MAX_LENGTH"] = 4
    assert upload(content=b"12345").status_code == 400
    app.config["EXAM_ATTACHMENT_MAX_LENGTH"] = 50 * 1024**2
    response = upload()
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["attachment_name"] == "测验资料.txt"
    path = Path(app.config["MEDIA_ROOT"]) / data["attachment"]
    assert path.read_bytes() == b"exam reference"
    assert client.get(endpoint, headers=bearer(student)).status_code == 404
    assert client.get(endpoint, headers=bearer(other_teacher)).status_code == 403
    preview = client.get(endpoint, headers=bearer(teacher))
    assert preview.data == b"exam reference"
    assert preview.headers["Content-Disposition"].startswith("inline")
    assert "no-store" in preview.headers["Cache-Control"]
    preview.close()
    download = client.get(endpoint + "?download=1", headers=bearer(teacher))
    assert download.headers["Content-Disposition"].startswith("attachment")
    download.close()

    replacement = upload(name="replacement.txt", content=b"new").get_json()["data"]
    new_path = Path(app.config["MEDIA_ROOT"]) / replacement["attachment"]
    assert not path.exists() and new_path.is_file()
    assert client.delete(endpoint, headers=bearer(other_teacher)).status_code == 403
    assert client.delete(endpoint, headers=bearer(teacher)).get_json()["data"]["attachment"] is None
    assert not new_path.exists()
    assert client.get(endpoint, headers=bearer(teacher)).status_code == 404
    data = upload().get_json()["data"]
    path = Path(app.config["MEDIA_ROOT"]) / data["attachment"]
    with app.app_context():
        db.session.get(Exam, exam["id"]).status = "PUBLISHED"
        db.session.commit()
    visible = client.get(endpoint, headers=bearer(student))
    assert visible.status_code == 200
    visible.close()
    assert client.get(endpoint, headers=bearer(outsider)).status_code == 403
    assert upload().status_code == 409
    assert client.delete(endpoint, headers=bearer(teacher)).status_code == 409
    with app.app_context():
        course = db.session.get(Course, context["course_id"])
        course.status = "OFFLINE"
        db.session.commit()
    assert client.get(endpoint, headers=bearer(student)).status_code == 404
    with app.app_context():
        db.session.get(Exam, exam["id"]).status = "DRAFT"
        db.session.commit()
    assert client.delete(f"/api/exams/{exam['id']}", headers=bearer(teacher)).status_code == 200
    assert not path.exists()


def test_private_teaching_attachments_cannot_use_development_media(app, client):
    from app import register_development_media
    app.config["DEBUG"] = True
    register_development_media(app)
    root = Path(app.config["MEDIA_ROOT"])
    for folder in ("exams", "homework"):
        target = root / folder / "private.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("private", encoding="utf-8")
        assert client.get(f"/media/{folder}/private.txt").status_code == 404
        assert client.get(f"/media/avatars/../{folder}/private.txt").status_code == 404


def test_attachment_paper_can_publish_without_questions_and_teacher_grades(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    student = login(client, context["student"])
    outsider = login(client, context["other_student"])
    other_teacher = login(client, context["other_teacher"])
    exam = create_exam(client, teacher, context["course_id"], exam_type="ATTACHMENT")
    base = f"/api/exams/{exam['id']}"
    assert client.post(base + "/publish", headers=bearer(teacher)).status_code >= 400
    assert client.post(base + "/attachment", headers=bearer(teacher),
                       data={"attachment": (BytesIO(b"reference paper"), "paper.txt")}).status_code == 200
    assert client.post(base + "/publish", headers=bearer(teacher)).status_code == 200
    assert client.get(base, headers=bearer(student)).get_json()["data"]["questions"] == []
    assert client.post(base + "/start", headers=bearer(outsider)).status_code == 403
    started = client.post(base + "/start", headers=bearer(student)).get_json()["data"]
    assert client.put(base + "/answers", headers=bearer(student), json={"answers": []}).status_code == 409
    assert client.post(base + "/submit", headers=bearer(student), json={"answers": []}).status_code == 409
    assert client.post(base + "/submission", headers=bearer(student), json={"content": ""}).status_code == 400
    saved = client.put(base + "/submission", headers=bearer(student),
                       data={"content": "第1题：答案", "attachment": (BytesIO(b"student answers"), "answer.txt")})
    assert saved.status_code == 200
    record = saved.get_json()["data"]
    assert record["status"] == "DOING" and record["attachment_name"] == "answer.txt"
    endpoint = f"/api/exams/records/{started['id']}"
    assert client.get(endpoint + "/attachment", headers=bearer(outsider)).status_code == 403
    assert client.get(endpoint + "/attachment", headers=bearer(other_teacher)).status_code == 403
    response = client.get(endpoint + "/attachment", headers=bearer(teacher))
    assert response.data == b"student answers"
    response.close()
    assert client.put(endpoint + "/grade", headers=bearer(teacher), json={"score": 85}).status_code == 409
    submitted = client.post(base + "/submission", headers=bearer(student), json={"content": "第1题：最终答案"})
    assert submitted.get_json()["data"]["score"] is None
    assert submitted.get_json()["data"]["status"] == "SUBMITTED"
    stats = client.get("/api/statistics", headers=bearer(student)).get_json()["data"]
    assert stats["completed_exams"] == 1 and stats["average_exam_percent"] == 0
    assert client.put(endpoint + "/grade", headers=bearer(other_teacher), json={"score": 85}).status_code == 403
    assert client.put(endpoint + "/grade", headers=bearer(teacher), json={"score": "NaN"}).status_code == 400
    assert client.put(endpoint + "/grade", headers=bearer(teacher), json={"score": 101}).status_code == 400
    graded = client.put(endpoint + "/grade", headers=bearer(teacher), json={"score": 85, "teacher_comment": "答题完整"})
    assert graded.status_code == 200 and graded.get_json()["data"]["status"] == "GRADED"
    for method in (client.put, client.post):
        assert method(base + "/submission", headers=bearer(student),
                      data={"content": "篡改", "attachment": (BytesIO(b"changed"), "changed.txt")}).status_code == 409
    assert client.post(base + "/start", headers=bearer(student)).status_code == 409
    unchanged = client.get(base, headers=bearer(student)).get_json()["data"]["record"]
    assert unchanged["content"] == "第1题：最终答案"
    assert unchanged["score"] == 85 and unchanged["teacher_comment"] == "答题完整"
    stats = client.get("/api/statistics", headers=bearer(student)).get_json()["data"]
    assert stats["completed_exams"] == 1 and stats["average_exam_percent"] == 85
    assert client.get("/api/exams/manage", headers=bearer(teacher)).get_json()["data"][0]["submitted_count"] == 1


def test_attachment_paper_expiry_only_submits_saved_content(app, client):
    context = create_context(app)
    teacher = login(client, context["teacher"])
    student = login(client, context["student"])
    exam = create_exam(client, teacher, context["course_id"], exam_type="ATTACHMENT", time_limit_minutes=1)
    base = f"/api/exams/{exam['id']}"
    client.post(base + "/attachment", headers=bearer(teacher), data={"attachment": (BytesIO(b"paper"), "paper.txt")})
    client.post(base + "/publish", headers=bearer(teacher))
    record = client.post(base + "/start", headers=bearer(student)).get_json()["data"]
    assert client.put(base + "/submission", headers=bearer(student), json={"content": "saved answer"}).status_code == 200
    with app.app_context():
        db.session.get(ExamRecord, record["id"]).started_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=2)
        db.session.commit()
    result = client.post(base + "/submission", headers=bearer(student),
                         data={"content": "late answer", "attachment": (BytesIO(b"late"), "late.txt")}).get_json()["data"]
    assert result["status"] == "SUBMITTED" and result["content"] == "saved answer"
    assert result["attachment"] is None and result["score"] is None
    assert result["duration_seconds"] == 60
