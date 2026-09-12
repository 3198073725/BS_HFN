from datetime import datetime, timezone
from unittest.mock import patch

from kombu.exceptions import OperationalError
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
    TeachingClass,
    TeachingClassCourse,
    TeachingClassStudent,
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
        classroom = TeachingClass(
            teacher_id=teacher.id,
            name="统计班级",
            description="验证班级教学统计",
        )
        db.session.add(classroom)
        db.session.flush()
        db.session.add_all(
            [
                TeachingClassStudent(class_id=classroom.id, student_id=student.id),
                TeachingClassCourse(class_id=classroom.id, course_id=course.id),
            ]
        )
        db.session.commit()
        return {
            "admin": admin.username,
            "teacher": teacher.username,
            "teacher_id": teacher.id,
            "student": student.username,
            "class_id": classroom.id,
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

    class_response = client.get(
        f"/api/statistics/classes/{context['class_id']}", headers=bearer(teacher)
    )
    assert class_response.status_code == 200
    class_data = class_response.get_json()["data"]
    assert class_data["member_count"] == 1
    assert class_data["course_count"] == 1
    assert class_data["overview"]["average_progress"] == 100.0
    assert class_data["overview"]["homework_submission_rate"] == 100.0
    assert class_data["overview"]["exam_completion_rate"] == 100.0
    assert class_data["courses"][0]["average_homework_percent"] == 80.0
    assert class_data["courses"][0]["average_exam_percent"] == 90.0
    assert client.get(
        f"/api/statistics/classes/{context['class_id']}", headers=bearer(student)
    ).status_code == 403

    admin_data = client.get(
        "/api/statistics", headers=bearer(admin)
    ).get_json()["data"]
    assert admin_data["users"] == 3
    assert admin_data["students"] == 1
    assert admin_data["teachers"] == 1
    assert admin_data["published_courses"] == 1

    with app.app_context():
        create_user("statistics_other_teacher", UserRole.TEACHER.value, "DT002")
        db.session.commit()
    other_teacher = login(client, "statistics_other_teacher")
    assert client.get(
        f"/api/statistics/classes/{context['class_id']}", headers=bearer(other_teacher)
    ).status_code == 403
    assert client.get(
        "/api/statistics/classes/999999", headers=bearer(teacher)
    ).status_code == 404


def test_admin_can_manage_video_operations_courses_classes_and_categories(app, client):
    context = create_context(app)
    admin = login(client, context["admin"])
    teacher = login(client, context["teacher"])

    assert client.get("/api/admin/videos", headers=bearer(teacher)).status_code == 403

    with app.app_context():
        chapter = db.session.scalar(db.select(Chapter).where(Chapter.title == "统计章节"))
        student = db.session.scalar(db.select(User).where(User.username == context["student"]))
        original = app.config["MEDIA_ROOT"] / "videos" / "original" / "failed.mp4"
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(b"failed-video-source")
        failed_video = Video(
            chapter_id=chapter.id,
            title="等待人工恢复的视频",
            original_name="failed.mp4",
            original_file="videos/original/failed.mp4",
            file_size=original.stat().st_size,
            status=VideoStatus.FAILED.value,
            process_step="TRANSCODING",
            error_message="转码进程异常退出",
        )
        classroom = TeachingClass(
            teacher_id=context["teacher_id"],
            name="管理员监管班级",
            description="验证班级监管操作",
        )
        db.session.add_all([failed_video, classroom])
        db.session.flush()
        db.session.add(TeachingClassStudent(class_id=classroom.id, student_id=student.id))
        db.session.commit()
        failed_video_id = failed_video.id
        classroom_id = classroom.id

    videos = client.get(
        "/api/admin/videos?status=FAILED&keyword=人工恢复",
        headers=bearer(admin),
    )
    assert videos.status_code == 200
    video_data = videos.get_json()["data"]
    assert video_data["summary"]["total"] == 2
    assert video_data["summary"]["FAILED"] == 1
    assert video_data["items"][0]["retryable"] is True
    assert video_data["items"][0]["original_exists"] is True
    assert "ffmpeg" in video_data["runtime"]

    app.config["VIDEO_PROCESSING_ASYNC"] = True
    with patch("app.tasks.video_tasks.process_video.delay") as delay:
        retried = client.post(
            f"/api/admin/videos/{failed_video_id}/retry",
            headers=bearer(admin),
        )
    assert retried.status_code == 202
    assert retried.get_json()["data"]["status"] == VideoStatus.PENDING.value
    assert retried.get_json()["data"]["process_step"] == "QUEUED"
    delay.assert_called_once_with(failed_video_id)

    assert client.post(
        f"/api/admin/videos/{failed_video_id}/retry",
        headers=bearer(admin),
    ).status_code == 409

    with app.app_context():
        failed_video = db.session.get(Video, failed_video_id)
        failed_video.status = VideoStatus.FAILED.value
        db.session.commit()
    with patch(
        "app.tasks.video_tasks.process_video.delay",
        side_effect=OperationalError("redis offline"),
    ):
        queue_failed = client.post(
            f"/api/admin/videos/{failed_video_id}/retry",
            headers=bearer(admin),
        )
    assert queue_failed.status_code == 503
    assert queue_failed.get_json()["data"]["status"] == VideoStatus.FAILED.value
    assert queue_failed.get_json()["data"]["process_step"] == "QUEUE"

    removed = client.delete(
        f"/api/admin/videos/{failed_video_id}",
        headers=bearer(admin),
    )
    assert removed.status_code == 200
    with app.app_context():
        assert db.session.get(Video, failed_video_id) is None
        assert not original.exists()

    courses = client.get("/api/admin/courses", headers=bearer(admin))
    assert courses.status_code == 200
    course = courses.get_json()["data"][0]
    assert course["ready_video_count"] == 1
    assert course["student_count"] == 1
    offline = client.put(
        f"/api/admin/courses/{course['id']}/status",
        headers=bearer(admin),
        json={"status": "OFFLINE"},
    )
    assert offline.status_code == 200
    assert offline.get_json()["data"]["status"] == CourseStatus.OFFLINE.value
    published = client.put(
        f"/api/admin/courses/{course['id']}/status",
        headers=bearer(admin),
        json={"status": "PUBLISHED"},
    )
    assert published.status_code == 200

    classes = client.get("/api/admin/classes?keyword=监管", headers=bearer(admin))
    assert classes.status_code == 200
    assert classes.get_json()["data"][0]["member_count"] == 1
    assert client.delete(
        f"/api/admin/classes/{classroom_id}",
        headers=bearer(admin),
    ).status_code == 200

    category = client.post(
        "/api/admin/categories",
        headers=bearer(admin),
        json={"name": "管理员新分类", "description": "用于后台维护", "sort_order": 9},
    )
    assert category.status_code == 201
    category_id = category.get_json()["data"]["id"]
    assert client.put(
        f"/api/admin/categories/{category_id}",
        headers=bearer(admin),
        json={"name": "管理员更新分类", "sort_order": 8},
    ).status_code == 200
    disabled = client.put(
        f"/api/admin/categories/{category_id}/status",
        headers=bearer(admin),
        json={"status": False},
    )
    assert disabled.status_code == 200
    assert disabled.get_json()["data"]["status"] is False
