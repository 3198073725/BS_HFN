import io
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from kombu.exceptions import OperationalError
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from app.constants import CourseStatus, UserRole
from app.extensions import db
from app.models import (
    Chapter,
    Course,
    CourseCategory,
    LearningRecord,
    Question,
    User,
    Video,
    VideoNote,
)
from app.services import generate_cover, generate_hls, probe_video, transcode_video
from app.services.file_service import save_original_video
from app.services.video_processing_service import process_video_sync


def create_sample_video(path, ffmpeg):
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:sample_rate=44100",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=60,
    )


@pytest.mark.skipif(os.getenv("RUN_FFMPEG_TEST") != "1", reason="set RUN_FFMPEG_TEST=1 to run FFmpeg integration")
def test_ffmpeg_pipeline(app, tmp_path):
    ffmpeg = app.config["FFMPEG_BIN"]
    ffprobe = app.config["FFPROBE_BIN"]
    source = tmp_path / "source.mp4"
    processed = tmp_path / "processed.mp4"
    cover = tmp_path / "cover.jpg"
    hls_dir = tmp_path / "hls"
    create_sample_video(source, ffmpeg)

    metadata = probe_video(source, ffprobe)
    assert metadata["streams"]
    transcode_video(source, processed, ffmpeg)
    playlist = generate_hls(processed, hls_dir, ffmpeg)
    generate_cover(processed, cover, ffmpeg)

    assert processed.is_file()
    assert playlist.is_file()
    assert list(hls_dir.glob("*.ts"))
    assert cover.is_file()


@pytest.mark.skipif(os.getenv("RUN_FFMPEG_TEST") != "1", reason="set RUN_FFMPEG_TEST=1 to run FFmpeg integration")
def test_teacher_upload_video_api(app, client, tmp_path):
    source = tmp_path / "lesson.mp4"
    create_sample_video(source, app.config["FFMPEG_BIN"])

    with app.app_context():
        teacher = User(
            username="video_teacher",
            password_hash=generate_password_hash("Teach123!"),
            real_name="视频教师",
            teacher_no="TV001",
            role=UserRole.TEACHER.value,
        )
        category = CourseCategory(name="视频课程")
        db.session.add_all([teacher, category])
        db.session.flush()
        course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="视频测试",
            status=CourseStatus.PUBLISHED.value,
        )
        db.session.add(course)
        db.session.flush()
        chapter = Chapter(course_id=course.id, title="第一章")
        db.session.add(chapter)
        db.session.commit()
        chapter_id = chapter.id

    login = client.post(
        "/api/auth/login",
        json={"account": "video_teacher", "password": "Teach123!"},
    )
    token = login.get_json()["data"]["access_token"]

    with source.open("rb") as handle:
        uploaded = client.post(
            "/api/videos/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "chapter_id": str(chapter_id),
                "title": "测试视频",
                "description": "真实 FFmpeg 上传链路",
                "video_file": (handle, "lesson.mp4"),
            },
            content_type="multipart/form-data",
        )

    assert uploaded.status_code == 201
    video = uploaded.get_json()["data"]
    assert video["status"] == "READY"
    assert video["hls_url"].endswith("index.m3u8")
    assert video["cover_url"].endswith(".jpg")

    status = client.get(
        f"/api/videos/{video['id']}/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status.status_code == 200
    assert status.get_json()["data"]["process_step"] == "FINISHED"


def test_async_upload_commits_before_enqueuing(app, client, monkeypatch):
    app.config["VIDEO_PROCESSING_ASYNC"] = True
    with app.app_context():
        teacher = User(
            username="async_teacher",
            password_hash=generate_password_hash("Teach123!"),
            real_name="异步教师",
            teacher_no="TA001",
            role=UserRole.TEACHER.value,
        )
        category = CourseCategory(name="异步课程")
        db.session.add_all([teacher, category])
        db.session.flush()
        course = Course(teacher_id=teacher.id, category_id=category.id, name="异步测试")
        db.session.add(course)
        db.session.flush()
        chapter = Chapter(course_id=course.id, title="异步章节")
        db.session.add(chapter)
        db.session.commit()
        chapter_id = chapter.id

    queued_ids = []

    def enqueue(video_id):
        persisted = db.session.get(Video, video_id)
        assert persisted is not None
        assert persisted.status == "PENDING"
        queued_ids.append(video_id)

    monkeypatch.setattr(
        "app.tasks.video_tasks.process_video",
        SimpleNamespace(delay=enqueue),
    )

    login = client.post(
        "/api/auth/login",
        json={"account": "async_teacher", "password": "Teach123!"},
    )
    token = login.get_json()["data"]["access_token"]
    rejected = client.post(
        "/api/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "chapter_id": str(chapter_id),
            "title": "非法排序",
            "sort_order": "-1",
            "video_file": (io.BytesIO(b"video"), "lesson.mp4"),
        },
        content_type="multipart/form-data",
    )
    assert rejected.status_code == 400

    oversized_sort = client.post(
        "/api/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "chapter_id": str(chapter_id),
            "title": "超大排序",
            "sort_order": "100001",
            "video_file": (io.BytesIO(b"video"), "lesson.mp4"),
        },
        content_type="multipart/form-data",
    )
    assert oversized_sort.status_code == 400

    uploaded = client.post(
        "/api/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "chapter_id": str(chapter_id),
            "title": "异步视频",
            "video_file": (io.BytesIO(b"queued-video"), "lesson.mp4"),
        },
        content_type="multipart/form-data",
    )

    assert uploaded.status_code == 202
    video = uploaded.get_json()["data"]
    assert video["status"] == "PENDING"
    assert queued_ids == [video["id"]]


def test_async_enqueue_failure_is_persisted(app, client, monkeypatch):
    app.config["VIDEO_PROCESSING_ASYNC"] = True
    with app.app_context():
        teacher = User(
            username="queue_teacher",
            password_hash=generate_password_hash("Teach123!"),
            real_name="队列教师",
            teacher_no="TQ001",
            role=UserRole.TEACHER.value,
        )
        category = CourseCategory(name="队列课程")
        db.session.add_all([teacher, category])
        db.session.flush()
        course = Course(teacher_id=teacher.id, category_id=category.id, name="队列测试")
        db.session.add(course)
        db.session.flush()
        chapter = Chapter(course_id=course.id, title="队列章节")
        db.session.add(chapter)
        db.session.commit()
        chapter_id = chapter.id

    def fail_enqueue(_video_id):
        raise OperationalError("broker offline")

    monkeypatch.setattr(
        "app.tasks.video_tasks.process_video",
        SimpleNamespace(delay=fail_enqueue),
    )
    token = client.post(
        "/api/auth/login",
        json={"account": "queue_teacher", "password": "Teach123!"},
    ).get_json()["data"]["access_token"]
    uploaded = client.post(
        "/api/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "chapter_id": str(chapter_id),
            "title": "队列失败视频",
            "video_file": (io.BytesIO(b"queued-video"), "lesson.mp4"),
        },
        content_type="multipart/form-data",
    )

    assert uploaded.status_code == 503
    video = uploaded.get_json()["data"]
    assert video["status"] == "FAILED"
    assert video["process_step"] == "QUEUE"


def test_video_file_validation_preserves_chinese_name_and_rejects_empty(tmp_path):
    stored, original_name = save_original_video(
        FileStorage(stream=io.BytesIO(b"video"), filename="课程介绍.mp4"),
        tmp_path,
    )
    assert stored.is_file()
    assert original_name == "课程介绍.mp4"

    with pytest.raises(ValueError, match="不能为空"):
        save_original_video(
            FileStorage(stream=io.BytesIO(b""), filename="empty.mp4"),
            tmp_path,
        )


def test_video_upload_rejects_unsupported_file_as_bad_request(app, client):
    with app.app_context():
        teacher = User(
            username="validation_teacher",
            password_hash=generate_password_hash("Teach123!"),
            real_name="校验教师",
            teacher_no="TV002",
            role=UserRole.TEACHER.value,
        )
        category = CourseCategory(name="上传校验课程")
        db.session.add_all([teacher, category])
        db.session.flush()
        course = Course(teacher_id=teacher.id, category_id=category.id, name="上传校验")
        db.session.add(course)
        db.session.flush()
        chapter = Chapter(course_id=course.id, title="第一章")
        db.session.add(chapter)
        db.session.commit()
        chapter_id = chapter.id

    login = client.post(
        "/api/auth/login",
        json={"account": "validation_teacher", "password": "Teach123!"},
    )
    token = login.get_json()["data"]["access_token"]
    uploaded = client.post(
        "/api/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "chapter_id": str(chapter_id),
            "title": "错误格式",
            "video_file": (io.BytesIO(b"not-video"), "lesson.txt"),
        },
        content_type="multipart/form-data",
    )

    assert uploaded.status_code == 400
    assert uploaded.get_json()["message"] == "不支持的视频格式"
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Video.id))) == 0


def test_failed_processing_cleans_generated_files(app, monkeypatch):
    with app.app_context():
        teacher = User(
            username="failed_video_teacher",
            password_hash=generate_password_hash("Teach123!"),
            real_name="失败测试教师",
            teacher_no="TF001",
            role=UserRole.TEACHER.value,
        )
        category = CourseCategory(name="失败处理课程")
        db.session.add_all([teacher, category])
        db.session.flush()
        course = Course(teacher_id=teacher.id, category_id=category.id, name="失败处理测试")
        db.session.add(course)
        db.session.flush()
        chapter = Chapter(course_id=course.id, title="失败处理章节")
        db.session.add(chapter)
        db.session.flush()

        media_root = Path(app.config["MEDIA_ROOT"])
        original_rel = "videos/original/broken.mp4"
        original_path = media_root / original_rel
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_bytes(b"not-a-real-video")
        video = Video(
            chapter_id=chapter.id,
            title="损坏视频",
            original_file=original_rel,
            processed_file="videos/processed/1/video.mp4",
            hls_path="videos/hls/1/index.m3u8",
            cover="videos/covers/1.jpg",
            status="PENDING",
        )
        db.session.add(video)
        db.session.commit()

        processed_dir = media_root / "videos" / "processed" / str(video.id)
        hls_dir = media_root / "videos" / "hls" / str(video.id)
        cover_path = media_root / "videos" / "covers" / f"{video.id}.jpg"
        processed_dir.mkdir(parents=True, exist_ok=True)
        hls_dir.mkdir(parents=True, exist_ok=True)
        cover_path.parent.mkdir(parents=True, exist_ok=True)
        (processed_dir / "partial.mp4").write_bytes(b"partial")
        (hls_dir / "partial.ts").write_bytes(b"partial")
        cover_path.write_bytes(b"partial")

        def fail_probe(*_args, **_kwargs):
            raise RuntimeError("probe failed")

        monkeypatch.setattr("app.services.video_processing_service.probe_video", fail_probe)
        result = process_video_sync(video.id)

        assert result.status == "FAILED"
        assert result.process_step == "PROBING"
        assert result.processed_file is None
        assert result.hls_path is None
        assert result.cover is None
        assert original_path.is_file()
        assert not processed_dir.exists()
        assert not hls_dir.exists()
        assert not cover_path.exists()


def test_celery_task_marks_pending_before_retry(monkeypatch):
    from app.tasks import video_tasks

    def fail_processing(_video_id, *, raise_on_error=False):
        raise video_tasks.VideoProcessingError("transcode failed")

    pending = []
    monkeypatch.setattr(video_tasks, "process_video_sync", fail_processing)
    monkeypatch.setattr(
        video_tasks,
        "mark_video_retry_pending",
        lambda video_id, message: pending.append((video_id, message)),
    )

    with pytest.raises(video_tasks.VideoProcessingError):
        video_tasks.process_video.run(99)

    assert pending[0][0] == 99
    assert "重试" in pending[0][1]


def test_teacher_can_manage_individual_video_lifecycle(app, client, monkeypatch):
    app.config["VIDEO_PROCESSING_ASYNC"] = True
    media_root = Path(app.config["MEDIA_ROOT"])
    original_dir = media_root / "videos" / "original"
    original_dir.mkdir(parents=True, exist_ok=True)

    with app.app_context():
        teacher = User(
            username="manage_video_teacher",
            password_hash=generate_password_hash("Teach123!"),
            real_name="视频管理教师",
            teacher_no="TMV001",
            role=UserRole.TEACHER.value,
        )
        other_teacher = User(
            username="other_video_teacher",
            password_hash=generate_password_hash("Teach123!"),
            real_name="其他视频教师",
            teacher_no="TMV002",
            role=UserRole.TEACHER.value,
        )
        student = User(
            username="manage_video_student",
            password_hash=generate_password_hash("Student123!"),
            real_name="视频学习学生",
            student_no="SMV001",
            role=UserRole.STUDENT.value,
        )
        category = CourseCategory(name="视频生命周期")
        db.session.add_all([teacher, other_teacher, student, category])
        db.session.flush()
        published_course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="发布中的课程",
            status=CourseStatus.PUBLISHED.value,
        )
        offline_course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="已下线课程",
            status=CourseStatus.OFFLINE.value,
        )
        other_course = Course(
            teacher_id=other_teacher.id,
            category_id=category.id,
            name="其他教师课程",
            status=CourseStatus.OFFLINE.value,
        )
        db.session.add_all([published_course, offline_course, other_course])
        db.session.flush()
        published_chapter = Chapter(course_id=published_course.id, title="发布章节")
        offline_chapter = Chapter(course_id=offline_course.id, title="维护章节")
        other_chapter = Chapter(course_id=other_course.id, title="其他章节")
        db.session.add_all([published_chapter, offline_chapter, other_chapter])
        db.session.flush()

        files = {
            "published": "videos/original/published.mp4",
            "failed": "videos/original/failed.mp4",
            "replace": "videos/original/replace.mp4",
            "other": "videos/original/other.mp4",
        }
        for relative_path in files.values():
            path = media_root / relative_path
            path.write_bytes(b"original-video")
        published_video = Video(
            chapter_id=published_chapter.id,
            title="发布视频",
            original_file=files["published"],
            status="READY",
        )
        failed_video = Video(
            chapter_id=offline_chapter.id,
            title="失败视频",
            original_file=files["failed"],
            status="FAILED",
            process_step="HLS",
            error_message="处理失败",
        )
        replace_target = Video(
            chapter_id=offline_chapter.id,
            title="待替换视频",
            original_file=files["replace"],
            status="READY",
        )
        other_video = Video(
            chapter_id=other_chapter.id,
            title="其他教师视频",
            original_file=files["other"],
            status="READY",
        )
        db.session.add_all([published_video, failed_video, replace_target, other_video])
        db.session.flush()
        db.session.add_all(
            [
                LearningRecord(
                    student_id=student.id,
                    video_id=replace_target.id,
                    current_time=10,
                    progress=50,
                ),
                VideoNote(
                    student_id=student.id,
                    video_id=replace_target.id,
                    video_time=5,
                    content="替换前笔记",
                ),
                Question(
                    student_id=student.id,
                    video_id=replace_target.id,
                    video_time=8,
                    title="替换前问题",
                    content="替换后应一并清理",
                ),
            ]
        )
        db.session.commit()
        ids = {
            "published": published_video.id,
            "failed": failed_video.id,
            "replace": replace_target.id,
            "other": other_video.id,
        }

    token = client.post(
        "/api/auth/login",
        json={"account": "manage_video_teacher", "password": "Teach123!"},
    ).get_json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    queued_ids = []
    monkeypatch.setattr(
        "app.tasks.video_tasks.process_video",
        SimpleNamespace(delay=lambda video_id: queued_ids.append(video_id)),
    )

    edited = client.put(
        f"/api/videos/{ids['published']}",
        headers=headers,
        json={"title": "更新后的视频", "description": "资料可直接维护", "sort_order": 8},
    )
    assert edited.status_code == 200
    assert edited.get_json()["data"]["sort_order"] == 8
    assert client.put(
        f"/api/videos/{ids['published']}",
        headers=headers,
        json={},
    ).status_code == 400
    assert client.put(
        f"/api/videos/{ids['other']}",
        headers=headers,
        json={"title": "越权修改"},
    ).status_code == 403

    retried = client.post(f"/api/videos/{ids['failed']}/retry", headers=headers)
    assert retried.status_code == 202
    assert retried.get_json()["data"]["status"] == "PENDING"
    assert queued_ids == [ids["failed"]]
    assert client.post(
        f"/api/videos/{ids['published']}/retry",
        headers=headers,
    ).status_code == 409

    assert client.delete(f"/api/videos/{ids['published']}", headers=headers).status_code == 409
    assert client.delete(f"/api/videos/{ids['other']}", headers=headers).status_code == 403
    invalid_replace = client.post(
        f"/api/videos/{ids['replace']}/replace",
        headers=headers,
        data={
            "title": "非法替换",
            "video_file": (io.BytesIO(b"not-video"), "replace.txt"),
        },
        content_type="multipart/form-data",
    )
    assert invalid_replace.status_code == 400
    with app.app_context():
        assert db.session.get(Video, ids["replace"]) is not None

    replaced = client.post(
        f"/api/videos/{ids['replace']}/replace",
        headers=headers,
        data={
            "title": "替换后的视频",
            "description": "使用新的源文件",
            "sort_order": "3",
            "video_file": (io.BytesIO(b"replacement-video"), "新的课程视频.mp4"),
        },
        content_type="multipart/form-data",
    )
    assert replaced.status_code == 202
    replacement = replaced.get_json()["data"]
    assert replacement["id"] != ids["replace"]
    assert replacement["original_name"] == "新的课程视频.mp4"
    assert queued_ids == [ids["failed"], replacement["id"]]
    with app.app_context():
        assert db.session.get(Video, ids["replace"]) is None
        assert db.session.scalar(
            db.select(db.func.count(LearningRecord.id)).where(
                LearningRecord.video_id == ids["replace"]
            )
        ) == 0
        assert db.session.scalar(
            db.select(db.func.count(VideoNote.id)).where(
                VideoNote.video_id == ids["replace"]
            )
        ) == 0
        assert db.session.scalar(
            db.select(db.func.count(Question.id)).where(
                Question.video_id == ids["replace"]
            )
        ) == 0
        new_video = db.session.get(Video, replacement["id"])
        new_original = media_root / new_video.original_file
        assert new_original.is_file()
        assert not (media_root / files["replace"]).exists()
        new_video.status = "READY"
        db.session.commit()

    assert client.delete(f"/api/videos/{replacement['id']}", headers=headers).status_code == 200
    with app.app_context():
        assert db.session.get(Video, replacement["id"]) is None
        assert not new_original.exists()
