from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from app.constants import CourseStatus, UserRole, VideoStatus
from app.extensions import db
from app.models import (
    Chapter,
    Course,
    CourseCategory,
    CourseStudent,
    Exam,
    ExamRecord,
    Homework,
    HomeworkSubmission,
    LearningRecord,
    Question,
    User,
    Video,
)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def create_user(username, role, number=None):
    values = {
        "username": username,
        "password_hash": generate_password_hash("Password123!"),
        "real_name": username,
        "role": role,
    }
    if role == UserRole.TEACHER.value:
        values["teacher_no"] = number
    elif role == UserRole.STUDENT.value:
        values["student_no"] = number
    user = User(**values)
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
        admin = create_user("dashboard_admin", UserRole.ADMIN.value)
        teacher = create_user("dashboard_teacher", UserRole.TEACHER.value, "DT001")
        student = create_user("dashboard_student", UserRole.STUDENT.value, "DS001")
        category = CourseCategory(name="统计测试")
        db.session.add(category)
        db.session.flush()
        course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="统计课程",
            status=CourseStatus.PUBLISHED.value,
        )
        db.session.add(course)
        db.session.flush()
        db.session.add(CourseStudent(course_id=course.id, student_id=student.id, status=True))
        chapter = Chapter(course_id=course.id, title="统计章节")
        db.session.add(chapter)
        db.session.flush()
        video = Video(
            chapter_id=chapter.id,
            title="统计视频",
            duration=60,
            status=VideoStatus.READY.value,
            hls_path="videos/hls/statistics/index.m3u8",
        )
        db.session.add(video)
        db.session.flush()
        db.session.add(
            LearningRecord(
                student_id=student.id,
                video_id=video.id,
                current_time=60,
                watch_duration=60,
                progress=100,
                status="COMPLETED",
            )
        )
        db.session.add(
            Question(
                student_id=student.id,
                video_id=video.id,
                video_time=10,
                title="统计问题",
                content="等待回答",
                status="WAITING",
            )
        )
        homework = Homework(
            course_id=course.id,
            teacher_id=teacher.id,
            title="统计作业",
            description="用于统计",
            total_score=100,
            status="PUBLISHED",
        )
        db.session.add(homework)
        db.session.flush()
        db.session.add(
            HomeworkSubmission(
                homework_id=homework.id,
                student_id=student.id,
                content="已完成",
                status="GRADED",
                score=80,
                submit_time=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        exam = Exam(
            course_id=course.id,
            teacher_id=teacher.id,
            title="统计测验",
            total_score=100,
            status="PUBLISHED",
        )
        db.session.add(exam)
        db.session.flush()
        db.session.add(
            ExamRecord(
                exam_id=exam.id,
                student_id=student.id,
                score=90,
                correct_count=9,
                wrong_count=1,
                status="SUBMITTED",
                started_at=datetime.now(timezone.utc).replace(tzinfo=None),
                submit_time=datetime.now(timezone.utc).replace(tzinfo=None),
                duration_seconds=300,
            )
        )
        db.session.commit()
        return {
            "admin": admin.username,
            "teacher": teacher.username,
            "teacher_id": teacher.id,
            "student": student.username,
        }


def test_notice_lifecycle_and_admin_user_management(app, client):
    context = create_context(app)
    admin = login(client, context["admin"])
    student = login(client, context["student"])

    assert client.get("/api/notices").get_json()["data"] == []
    assert client.post(
        "/api/notices",
        headers=bearer(student),
        json={"title": "越权公告", "content": "不应创建"},
    ).status_code == 403
    created = client.post(
        "/api/notices",
        headers=bearer(admin),
        json={"title": "系统维护通知", "content": "今晚进行例行维护。"},
    )
    assert created.status_code == 201
    notice_id = created.get_json()["data"]["id"]
    assert client.get("/api/notices").get_json()["data"] == []

    published = client.put(
        f"/api/notices/{notice_id}/status",
        headers=bearer(admin),
        json={"status": "PUBLISHED"},
    )
    assert published.status_code == 200
    public = client.get("/api/notices").get_json()["data"]
    assert public[0]["title"] == "系统维护通知"
    assert client.put(
        f"/api/notices/{notice_id}",
        headers=bearer(admin),
        json={"title": "发布后修改"},
    ).status_code == 409
    assert client.delete(
        f"/api/notices/{notice_id}", headers=bearer(admin)
    ).status_code == 409

    offline = client.put(
        f"/api/notices/{notice_id}/status",
        headers=bearer(admin),
        json={"status": "OFFLINE"},
    )
    assert offline.status_code == 200
    assert client.get("/api/notices").get_json()["data"] == []
    assert client.put(
        f"/api/notices/{notice_id}",
        headers=bearer(admin),
        json={"content": "调整后的维护说明。"},
    ).status_code == 200

    users = client.get(
        "/api/admin/users?role=TEACHER&keyword=dashboard",
        headers=bearer(admin),
    )
    assert users.status_code == 200
    assert len(users.get_json()["data"]) == 1
    disabled = client.put(
        f"/api/admin/users/{context['teacher_id']}/status",
        headers=bearer(admin),
        json={"status": False},
    )
    assert disabled.status_code == 200
    assert disabled.get_json()["data"]["status"] is False
    denied_login = client.post(
        "/api/auth/login",
        json={"account": context["teacher"], "password": "Password123!"},
    )
    assert denied_login.status_code == 401


def test_role_overviews_and_teacher_course_statistics(app, client):
    context = create_context(app)
    admin = login(client, context["admin"])
    teacher = login(client, context["teacher"])
    student = login(client, context["student"])

    student_data = client.get(
        "/api/statistics", headers=bearer(student)
    ).get_json()["data"]
    assert student_data["joined_courses"] == 1
    assert student_data["completed_videos"] == 1
    assert student_data["average_video_progress"] == 100.0
    assert student_data["average_homework_percent"] == 80.0
    assert student_data["average_exam_percent"] == 90.0

    teacher_data = client.get(
        "/api/statistics", headers=bearer(teacher)
    ).get_json()["data"]
    assert teacher_data["courses"] == 1
    assert teacher_data["active_students"] == 1
    assert teacher_data["ready_videos"] == 1
    assert teacher_data["waiting_questions"] == 1
    course_data = client.get(
        "/api/statistics/courses", headers=bearer(teacher)
    ).get_json()["data"]
    assert course_data[0]["average_progress"] == 100.0
    assert course_data[0]["average_homework_percent"] == 80.0
    assert course_data[0]["average_exam_percent"] == 90.0

    admin_data = client.get(
        "/api/statistics", headers=bearer(admin)
    ).get_json()["data"]
    assert admin_data["users"] == 3
    assert admin_data["students"] == 1
    assert admin_data["teachers"] == 1
    assert admin_data["published_courses"] == 1
