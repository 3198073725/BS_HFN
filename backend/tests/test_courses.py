from pathlib import Path

from werkzeug.security import generate_password_hash

from app.constants import UserRole
from app.extensions import db
from app.models import Chapter, Course, CourseCategory, Homework, User, Video


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def create_user(username, password, role, number):
    values = {
        "username": username,
        "password_hash": generate_password_hash(password),
        "real_name": username,
        "role": role,
    }
    values["teacher_no" if role == UserRole.TEACHER.value else "student_no"] = number
    user = User(**values)
    db.session.add(user)
    db.session.commit()
    return user


def login(client, account, password):
    response = client.post("/api/auth/login", json={"account": account, "password": password})
    assert response.status_code == 200
    return response.get_json()["data"]["access_token"]


def test_course_chapter_publish_and_permissions(app, client):
    with app.app_context():
        category = CourseCategory(name="计算机", sort_order=0)
        db.session.add(category)
        db.session.commit()
        category_id = category.id
        create_user("teacher01", "Teach123!", UserRole.TEACHER.value, "T001")
        create_user("teacher02", "Teach123!", UserRole.TEACHER.value, "T002")
        create_user("student01", "Study123!", UserRole.STUDENT.value, "S001")

    teacher = login(client, "teacher01", "Teach123!")
    other_teacher = login(client, "teacher02", "Teach123!")
    student = login(client, "student01", "Study123!")

    forbidden = client.post(
        "/api/courses",
        headers=bearer(student),
        json={"name": "越权课程", "category_id": category_id},
    )
    assert forbidden.status_code == 403

    created = client.post(
        "/api/courses",
        headers=bearer(teacher),
        json={"name": "Python 基础", "category_id": category_id, "description": "入门课程"},
    )
    assert created.status_code == 201
    course_id = created.get_json()["data"]["id"]

    assert client.get("/api/courses").get_json()["data"] == []

    publish_without_chapter = client.post(
        f"/api/courses/{course_id}/publish",
        headers=bearer(teacher),
    )
    assert publish_without_chapter.status_code == 409

    chapter = client.post(
        f"/api/courses/{course_id}/chapters",
        headers=bearer(teacher),
        json={"title": "第一章", "sort_order": 1},
    )
    assert chapter.status_code == 201
    chapter_id = chapter.get_json()["data"]["id"]

    with app.app_context():
        failed_video = Video(chapter_id=chapter_id, title="失败视频", status="FAILED")
        db.session.add(failed_video)
        db.session.commit()
        failed_video_id = failed_video.id

    denied = client.put(
        f"/api/courses/{course_id}",
        headers=bearer(other_teacher),
        json={"name": "不应修改"},
    )
    assert denied.status_code == 403

    published = client.post(f"/api/courses/{course_id}/publish", headers=bearer(teacher))
    assert published.status_code == 200
    assert published.get_json()["data"]["status"] == "PUBLISHED"

    public_list = client.get("/api/courses")
    assert public_list.status_code == 200
    assert public_list.get_json()["data"][0]["name"] == "Python 基础"

    detail = client.get(f"/api/courses/{course_id}")
    assert detail.status_code == 200
    assert detail.get_json()["data"]["chapters"][0]["title"] == "第一章"
    assert detail.get_json()["data"]["chapters"][0]["videos"] == []

    teacher_detail = client.get(f"/api/courses/{course_id}", headers=bearer(teacher))
    assert teacher_detail.get_json()["data"]["chapters"][0]["videos"][0]["status"] == "FAILED"
    assert client.get(f"/api/videos/{failed_video_id}/status").status_code == 404

    assert client.post(f"/api/courses/{course_id}/publish", headers=bearer(teacher)).status_code == 409
    assert client.post(f"/api/courses/{course_id}/offline", headers=bearer(teacher)).status_code == 200
    assert client.post(f"/api/courses/{course_id}/offline", headers=bearer(teacher)).status_code == 409
    assert client.get("/api/courses").get_json()["data"] == []
    assert client.post(f"/api/courses/{course_id}/publish", headers=bearer(teacher)).status_code == 200


def test_deleting_chapter_cleans_video_files(app, client):
    with app.app_context():
        category = CourseCategory(name="清理测试分类")
        teacher = create_user("cleanup_teacher", "Teach123!", UserRole.TEACHER.value, "TC001")
        db.session.add(category)
        db.session.flush()
        course = Course(teacher_id=teacher.id, category_id=category.id, name="清理测试课程")
        db.session.add(course)
        db.session.flush()
        chapter = Chapter(course_id=course.id, title="待删除章节")
        db.session.add(chapter)
        db.session.flush()
        video = Video(
            chapter_id=chapter.id,
            title="待删除视频",
            original_file="videos/original/delete-me.mp4",
            status="FAILED",
        )
        db.session.add(video)
        db.session.commit()
        course_id = course.id
        chapter_id = chapter.id
        video_id = video.id

        media_root = Path(app.config["MEDIA_ROOT"])
        original = media_root / video.original_file
        processed = media_root / "videos" / "processed" / str(video.id) / "video.mp4"
        hls = media_root / "videos" / "hls" / str(video.id) / "index.m3u8"
        cover = media_root / "videos" / "covers" / f"{video.id}.jpg"
        for path in (original, processed, hls, cover):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"temporary")

    teacher_token = login(client, "cleanup_teacher", "Teach123!")
    deleted = client.delete(
        f"/api/courses/{course_id}/chapters/{chapter_id}",
        headers=bearer(teacher_token),
    )

    assert deleted.status_code == 200
    with app.app_context():
        assert db.session.get(Video, video_id) is None
    assert not original.exists()
    assert not processed.exists()
    assert not hls.exists()
    assert not cover.exists()


def test_deleting_draft_course_cleans_homework_attachments(app, client):
    with app.app_context():
        category = CourseCategory(name="作业附件清理分类")
        teacher = create_user("attachment_teacher", "Teach123!", UserRole.TEACHER.value, "TA001")
        db.session.add(category)
        db.session.flush()
        course = Course(teacher_id=teacher.id, category_id=category.id, name="待删除草稿课程")
        db.session.add(course)
        db.session.flush()
        homework = Homework(
            course_id=course.id,
            teacher_id=teacher.id,
            title="待清理作业",
            description="附件应随课程清理",
            attachment=f"homework/pending/teacher/file.pdf",
        )
        db.session.add(homework)
        db.session.flush()
        homework_dir = Path(app.config["MEDIA_ROOT"]) / "homework" / str(homework.id)
        attachment = homework_dir / "teacher" / "file.pdf"
        attachment.parent.mkdir(parents=True, exist_ok=True)
        attachment.write_bytes(b"temporary homework attachment")
        homework.attachment = attachment.relative_to(app.config["MEDIA_ROOT"]).as_posix()
        db.session.commit()
        course_id = course.id
        homework_id = homework.id

    teacher_token = login(client, "attachment_teacher", "Teach123!")
    deleted = client.delete(f"/api/courses/{course_id}", headers=bearer(teacher_token))
    assert deleted.status_code == 200
    assert not homework_dir.exists()
    with app.app_context():
        assert db.session.get(Homework, homework_id) is None
