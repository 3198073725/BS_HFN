import io
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from kombu.exceptions import OperationalError
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from app.constants import UserRole
from app.extensions import db
from app.models import Chapter, Course, CourseCategory, User, Video
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
        course = Course(teacher_id=teacher.id, category_id=category.id, name="视频测试")
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
