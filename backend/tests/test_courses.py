from io import BytesIO
from pathlib import Path

from werkzeug.security import generate_password_hash

from app.constants import UserRole, VideoStatus
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

    invalid_category = client.post(
        "/api/courses",
        headers=bearer(teacher),
        json={"name": "错误分类", "category_id": True},
    )
    assert invalid_category.status_code == 400

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

    empty_update = client.put(
        f"/api/courses/{course_id}",
        headers=bearer(teacher),
        json={},
    )
    assert empty_update.status_code == 400

    invalid_chapter = client.post(
        f"/api/courses/{course_id}/chapters",
        headers=bearer(teacher),
        json={"title": "错误排序章节", "sort_order": -1},
    )
    assert invalid_chapter.status_code == 400

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

    published_update = client.put(
        f"/api/courses/{course_id}",
        headers=bearer(teacher),
        json={"name": "Python 发布维护版"},
    )
    assert published_update.status_code == 200
    assert published_update.get_json()["data"]["name"] == "Python 发布维护版"
    published_chapter = client.post(
        f"/api/courses/{course_id}/chapters",
        headers=bearer(teacher),
        json={"title": "发布中新增章节", "sort_order": 2},
    )
    assert published_chapter.status_code == 201
    assert client.put(
        f"/api/courses/{course_id}/chapters/{published_chapter.get_json()['data']['id']}",
        headers=bearer(teacher),
        json={"title": "发布中调整章节"},
    ).status_code == 200
    assert client.delete(
        f"/api/courses/{course_id}/chapters/{published_chapter.get_json()['data']['id']}",
        headers=bearer(teacher),
    ).status_code == 409

    assert client.post(f"/api/courses/{course_id}/offline", headers=bearer(teacher)).status_code == 200
    assert client.post(f"/api/courses/{course_id}/offline", headers=bearer(teacher)).status_code == 409
    assert client.get("/api/courses").get_json()["data"] == []

    offline_update = client.put(
        f"/api/courses/{course_id}",
        headers=bearer(teacher),
        json={"name": "Python 下线维护版"},
    )
    assert offline_update.status_code == 200
    assert offline_update.get_json()["data"]["name"] == "Python 下线维护版"
    assert client.delete(
        f"/api/courses/{course_id}/chapters/{published_chapter.get_json()['data']['id']}",
        headers=bearer(teacher),
    ).status_code == 200

    republished = client.post(f"/api/courses/{course_id}/publish", headers=bearer(teacher))
    assert republished.status_code == 200
    assert republished.get_json()["data"]["name"] == "Python 下线维护版"


def test_public_courses_support_combined_category_teacher_and_keyword_filters(app, client):
    with app.app_context():
        category_a = CourseCategory(name="编程开发", sort_order=0)
        category_b = CourseCategory(name="计算机基础", sort_order=1)
        db.session.add_all([category_a, category_b])
        db.session.flush()
        teacher_a = create_user("filter_teacher_a", "Teach123!", UserRole.TEACHER.value, "FT001")
        teacher_a.real_name = "陈老师"
        teacher_b = create_user("filter_teacher_b", "Teach123!", UserRole.TEACHER.value, "FT002")
        teacher_b.real_name = "王老师"
        db.session.add_all([
            Course(teacher_id=teacher_a.id, category_id=category_a.id, name="Python 数据分析",
                   description="使用 pandas 处理数据", status="PUBLISHED"),
            Course(teacher_id=teacher_b.id, category_id=category_a.id, name="Java Web 开发",
                   description="后端开发与接口设计", status="PUBLISHED"),
            Course(teacher_id=teacher_a.id, category_id=category_b.id, name="操作系统基础",
                   description="进程与内存", status="PUBLISHED"),
            Course(teacher_id=teacher_b.id, category_id=category_b.id, name="未发布 Python",
                   description="不应出现在公开筛选中", status="DRAFT"),
        ])
        db.session.commit()
        category_a_id = category_a.id
        teacher_a_id = teacher_a.id
        teacher_b_id = teacher_b.id

    teachers = client.get("/api/courses/teachers")
    assert teachers.status_code == 200
    assert {item["id"]: item["name"] for item in teachers.get_json()["data"]} == {
        teacher_a_id: "陈老师",
        teacher_b_id: "王老师",
    }
    by_category = client.get(f"/api/courses?category_id={category_a_id}").get_json()["data"]
    assert {item["name"] for item in by_category} == {"Python 数据分析", "Java Web 开发"}
    by_teacher = client.get(f"/api/courses?teacher_id={teacher_b_id}").get_json()["data"]
    assert [item["name"] for item in by_teacher] == ["Java Web 开发"]
    by_name = client.get("/api/courses?keyword=Python").get_json()["data"]
    assert [item["name"] for item in by_name] == ["Python 数据分析"]
    by_description = client.get("/api/courses?keyword=%E5%90%8E%E7%AB%AF").get_json()["data"]
    assert [item["name"] for item in by_description] == ["Java Web 开发"]
    combined = client.get(
        f"/api/courses?category_id={category_a_id}&teacher_id={teacher_a_id}&keyword=Python"
    ).get_json()["data"]
    assert [item["name"] for item in combined] == ["Python 数据分析"]
    assert client.get("/api/courses?teacher_id=abc").status_code == 400
    assert client.get("/api/courses?teacher_id=0").status_code == 400
    assert client.get(f"/api/courses?keyword={'x' * 101}").status_code == 400


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
            status=VideoStatus.PROCESSING.value,
            process_step="TRANSCODING",
            task_id="chapter-delete-task",
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
    revoked = []
    app.extensions["celery"] = type("FakeCelery", (), {
        "control": type("FakeControl", (), {
            "revoke": staticmethod(lambda task_id, **kwargs: revoked.append((task_id, kwargs))),
        })(),
    })()
    deleted = client.delete(
        f"/api/courses/{course_id}/chapters/{chapter_id}",
        headers=bearer(teacher_token),
    )

    assert deleted.status_code == 200
    assert revoked == [("chapter-delete-task", {"terminate": True, "signal": "SIGTERM"})]
    with app.app_context():
        assert db.session.get(Video, video_id) is None
    assert not original.exists()
    assert not processed.exists()
    assert not hls.exists()
    assert not cover.exists()


def test_teacher_can_manage_validated_course_cover(app, client):
    with app.app_context():
        category = CourseCategory(name="课程封面分类")
        teacher = create_user("cover_teacher", "Teach123!", UserRole.TEACHER.value, "TC101")
        other = create_user("other_cover_teacher", "Teach123!", UserRole.TEACHER.value, "TC102")
        db.session.add(category)
        db.session.flush()
        course = Course(teacher_id=teacher.id, category_id=category.id, name="封面测试课程")
        db.session.add(course)
        db.session.commit()
        course_id = course.id

    teacher_token = login(client, "cover_teacher", "Teach123!")
    other_token = login(client, "other_cover_teacher", "Teach123!")

    denied = client.post(
        f"/api/courses/{course_id}/cover",
        headers=bearer(other_token),
        data={"cover": (BytesIO(b"\x89PNG\r\n\x1a\nvalid"), "denied.png")},
    )
    assert denied.status_code == 403

    disguised_file = client.post(
        f"/api/courses/{course_id}/cover",
        headers=bearer(teacher_token),
        data={"cover": (BytesIO(b"not an image"), "fake.png")},
    )
    assert disguised_file.status_code == 400
    assert "内容与图片格式不匹配" in disguised_file.get_json()["message"]

    first_upload = client.post(
        f"/api/courses/{course_id}/cover",
        headers=bearer(teacher_token),
        data={"cover": (BytesIO(b"\x89PNG\r\n\x1a\nfirst-cover"), "first.png")},
    )
    assert first_upload.status_code == 200
    first_path = first_upload.get_json()["data"]["cover"]
    assert first_upload.get_json()["data"]["cover_url"] == f"/media/{first_path}"
    first_file = Path(app.config["MEDIA_ROOT"]) / first_path
    assert first_file.is_file()

    replacement = client.post(
        f"/api/courses/{course_id}/cover",
        headers=bearer(teacher_token),
        data={"cover": (BytesIO(b"\xff\xd8\xffreplacement"), "replacement.jpg")},
    )
    assert replacement.status_code == 200
    replacement_path = replacement.get_json()["data"]["cover"]
    replacement_file = Path(app.config["MEDIA_ROOT"]) / replacement_path
    assert replacement_file.is_file()
    assert not first_file.exists()

    removed = client.delete(
        f"/api/courses/{course_id}/cover",
        headers=bearer(teacher_token),
    )
    assert removed.status_code == 200
    assert removed.get_json()["data"]["cover"] is None
    assert removed.get_json()["data"]["cover_url"] is None
    assert not replacement_file.exists()


def test_course_cover_size_limit_and_course_delete_cleanup(app, client):
    with app.app_context():
        app.config["COURSE_COVER_MAX_LENGTH"] = 16
        category = CourseCategory(name="封面清理分类")
        teacher = create_user("cover_cleanup", "Teach123!", UserRole.TEACHER.value, "TC103")
        db.session.add(category)
        db.session.flush()
        course = Course(teacher_id=teacher.id, category_id=category.id, name="封面清理课程")
        db.session.add(course)
        db.session.commit()
        course_id = course.id

    teacher_token = login(client, "cover_cleanup", "Teach123!")
    oversized = client.post(
        f"/api/courses/{course_id}/cover",
        headers=bearer(teacher_token),
        data={"cover": (BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 20), "large.png")},
    )
    assert oversized.status_code == 400
    assert "课程封面不能超过" in oversized.get_json()["message"]

    with app.app_context():
        app.config["COURSE_COVER_MAX_LENGTH"] = 5 * 1024**2
    uploaded = client.post(
        f"/api/courses/{course_id}/cover",
        headers=bearer(teacher_token),
        data={"cover": (BytesIO(b"\x89PNG\r\n\x1a\ncleanup-cover"), "cleanup.png")},
    )
    cover_path = uploaded.get_json()["data"]["cover"]
    cover_file = Path(app.config["MEDIA_ROOT"]) / cover_path
    assert cover_file.is_file()

    deleted = client.delete(f"/api/courses/{course_id}", headers=bearer(teacher_token))
    assert deleted.status_code == 200
    assert not cover_file.exists()


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
