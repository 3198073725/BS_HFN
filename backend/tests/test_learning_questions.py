from werkzeug.security import generate_password_hash

from app.constants import CourseStatus, UserRole, VideoStatus
from app.extensions import db
from app.models import Chapter, Course, CourseCategory, User, Video


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


def create_learning_context(app):
    with app.app_context():
        teacher = create_user("teacher_learning", UserRole.TEACHER.value, "TL001")
        other_teacher = create_user("teacher_other", UserRole.TEACHER.value, "TL002")
        student = create_user("student_learning", UserRole.STUDENT.value, "SL001")
        other_student = create_user("student_other", UserRole.STUDENT.value, "SL002")
        category = CourseCategory(name="学习测试")
        db.session.add(category)
        db.session.flush()
        course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="阶段五测试课程",
            status=CourseStatus.PUBLISHED.value,
        )
        db.session.add(course)
        db.session.flush()
        chapter = Chapter(course_id=course.id, title="第一章")
        db.session.add(chapter)
        db.session.flush()
        video = Video(
            chapter_id=chapter.id,
            title="学习记录视频",
            duration=100,
            status=VideoStatus.READY.value,
            hls_path="videos/hls/test/index.m3u8",
        )
        db.session.add(video)
        db.session.add(
            Video(
                chapter_id=chapter.id,
                title="尚未学习的视频",
                duration=50,
                status=VideoStatus.READY.value,
                hls_path="videos/hls/test-2/index.m3u8",
            )
        )
        db.session.commit()
        return {
            "course_id": course.id,
            "video_id": video.id,
            "teacher": teacher.username,
            "other_teacher": other_teacher.username,
            "student": student.username,
            "other_student": other_student.username,
        }


def test_join_favorite_progress_and_notes(app, client):
    context = create_learning_context(app)
    student = login(client, context["student"])
    other_student = login(client, context["other_student"])
    teacher = login(client, context["teacher"])
    course_url = f"/api/learning/courses/{context['course_id']}"
    progress_url = f"/api/learning/videos/{context['video_id']}/progress"
    notes_url = f"/api/learning/videos/{context['video_id']}/notes"

    assert client.post(f"{course_url}/join", headers=bearer(teacher)).status_code == 403
    assert client.get(progress_url, headers=bearer(student)).status_code == 403

    joined = client.post(f"{course_url}/join", headers=bearer(student))
    assert joined.status_code == 201
    assert joined.get_json()["data"]["joined"] is True
    assert client.post(f"{course_url}/join", headers=bearer(student)).status_code == 409

    favorite = client.post(f"{course_url}/favorite", headers=bearer(student))
    assert favorite.status_code == 201
    assert client.post(f"{course_url}/favorite", headers=bearer(student)).status_code == 409

    joined_courses = client.get("/api/learning/courses", headers=bearer(student))
    assert joined_courses.status_code == 200
    assert joined_courses.get_json()["data"][0]["learning_progress"] == 0.0
    assert len(client.get("/api/learning/favorites", headers=bearer(student)).get_json()["data"]) == 1

    invalid_progress = client.put(
        progress_url,
        headers=bearer(student),
        json={"current_time": 1000, "watch_duration_delta": 1},
    )
    assert invalid_progress.status_code == 400

    first_progress = client.put(
        progress_url,
        headers=bearer(student),
        json={"current_time": 45, "watch_duration_delta": 12},
    )
    assert first_progress.status_code == 200
    assert first_progress.get_json()["data"]["progress"] == 45.0
    assert first_progress.get_json()["data"]["status"] == "LEARNING"

    completed = client.put(
        progress_url,
        headers=bearer(student),
        json={"current_time": 95, "watch_duration_delta": 15},
    )
    assert completed.get_json()["data"]["status"] == "COMPLETED"
    assert completed.get_json()["data"]["watch_duration"] == 27
    assert client.get(progress_url, headers=bearer(student)).get_json()["data"]["current_time"] == 95.0
    updated_courses = client.get("/api/learning/courses", headers=bearer(student)).get_json()["data"]
    assert updated_courses[0]["learning_progress"] == 47.5

    note = client.post(
        notes_url,
        headers=bearer(student),
        json={"video_time": 46.5, "content": "这里需要重点复习"},
    )
    assert note.status_code == 201
    note_id = note.get_json()["data"]["id"]
    assert len(client.get(notes_url, headers=bearer(student)).get_json()["data"]) == 1

    updated_note = client.put(
        f"/api/learning/notes/{note_id}",
        headers=bearer(student),
        json={"content": "更新后的重点笔记"},
    )
    assert updated_note.status_code == 200
    assert updated_note.get_json()["data"]["content"] == "更新后的重点笔记"
    assert client.delete(f"/api/learning/notes/{note_id}", headers=bearer(other_student)).status_code == 403
    assert client.delete(f"/api/learning/notes/{note_id}", headers=bearer(student)).status_code == 200

    assert client.delete(f"{course_url}/join", headers=bearer(student)).status_code == 200
    assert client.get(progress_url, headers=bearer(student)).status_code == 403
    assert client.delete(f"{course_url}/favorite", headers=bearer(student)).status_code == 200
    state = client.get(f"{course_url}/state", headers=bearer(student)).get_json()["data"]
    assert state == {"course_id": context["course_id"], "joined": False, "favorited": False}


def test_question_and_teacher_answer_permissions(app, client):
    context = create_learning_context(app)
    student = login(client, context["student"])
    other_student = login(client, context["other_student"])
    teacher = login(client, context["teacher"])
    other_teacher = login(client, context["other_teacher"])

    client.post(
        f"/api/learning/courses/{context['course_id']}/join",
        headers=bearer(student),
    )
    invalid_video = client.post(
        "/api/questions",
        headers=bearer(student),
        json={
            "video_id": True,
            "video_time": 1,
            "title": "错误视频参数",
            "content": "布尔值不能作为视频编号。",
        },
    )
    assert invalid_video.status_code == 400

    question = client.post(
        "/api/questions",
        headers=bearer(student),
        json={
            "video_id": context["video_id"],
            "video_time": 33,
            "title": "这一段为什么这样处理？",
            "content": "希望老师解释这里的核心思路。",
        },
    )
    assert question.status_code == 201
    question_id = question.get_json()["data"]["id"]
    assert question.get_json()["data"]["status"] == "WAITING"

    assert len(client.get("/api/questions", headers=bearer(student)).get_json()["data"]) == 1
    assert len(client.get("/api/questions?status=WAITING", headers=bearer(teacher)).get_json()["data"]) == 1
    assert client.get("/api/questions", headers=bearer(other_teacher)).get_json()["data"] == []
    assert client.get(f"/api/questions/{question_id}", headers=bearer(other_student)).status_code == 403
    assert client.get(f"/api/questions/{question_id}", headers=bearer(other_teacher)).status_code == 403
    assert client.post(
        f"/api/questions/{question_id}/answer",
        headers=bearer(student),
        json={"content": "学生不能回答"},
    ).status_code == 403

    answered = client.post(
        f"/api/questions/{question_id}/answer",
        headers=bearer(teacher),
        json={"content": "这里需要先理解课程中的前置概念。"},
    )
    assert answered.status_code == 201
    assert answered.get_json()["data"]["status"] == "ANSWERED"
    assert answered.get_json()["data"]["answer"]["teacher_name"] == context["teacher"]
    assert client.post(
        f"/api/questions/{question_id}/answer",
        headers=bearer(teacher),
        json={"content": "重复回答"},
    ).status_code == 409

    edited = client.put(
        f"/api/questions/{question_id}/answer",
        headers=bearer(teacher),
        json={"content": "补充后的正式回答。"},
    )
    assert edited.status_code == 200
    assert edited.get_json()["data"]["answer"]["content"] == "补充后的正式回答。"

    closed = client.post(f"/api/questions/{question_id}/close", headers=bearer(student))
    assert closed.status_code == 200
    assert closed.get_json()["data"]["status"] == "CLOSED"
    assert client.post(f"/api/questions/{question_id}/close", headers=bearer(student)).status_code == 409
    assert client.put(
        f"/api/questions/{question_id}/answer",
        headers=bearer(teacher),
        json={"content": "关闭后不应再修改"},
    ).status_code == 409
