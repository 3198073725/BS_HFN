import json
import os
import subprocess

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import Chapter, Course, CourseStudent, Exam, ExamAnswer, ExamQuestion, ExamRecord, Homework, HomeworkSubmission, TeachingClass, User, Video
from scripts.demo_catalog import COURSES, DEMO_PASSWORD
from scripts.seed_demo import check_demo, seed_demo_data


@pytest.fixture
def demo_assets(app):
    """Small non-playable fixture bytes; real media is validated separately."""
    root = app.config["MEDIA_ROOT"] / "defense_assets"
    manifest = {"courses": {}}
    for key, *_rest in COURSES:
        directory = root / key
        (directory / "hls").mkdir(parents=True)
        for filename in ("cover.png", "cover.jpg", "source.mp4", "hls/index.m3u8"):
            (directory / filename).write_bytes(b"demo-seed-unit-test-fixture")
        manifest["courses"][key] = {"duration": 30, "width": 960, "height": 540, "file_size": 27}
    (root / "attachments").mkdir()
    for filename in ("lab-guide.pdf", "lab-report.txt", "result.png", "source-code.zip"):
        (root / "attachments" / filename).write_bytes(b"demo-seed-unit-test-fixture")
    for index in range(4):
        (root / f"teacher-{index}.png").write_bytes(b"avatar-fixture")
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_demo_seed_rich_consistent_idempotent_and_preserves_existing(app, demo_assets):
    with app.app_context():
        existing = User(username="existing_student", real_name="原学生", role="STUDENT", password_hash=generate_password_hash("Original123!"))
        db.session.add(existing)
        db.session.commit()
        old_hash = existing.password_hash
    report = seed_demo_data(app)
    assert report["counts"]["User"] == 36
    assert report["counts"]["Course"] == 12
    assert report["counts"]["TeachingClass"] == 14
    assert report["counts"]["Video"] == 53
    assert report["counts"]["Homework"] == 21
    assert report["counts"]["Exam"] == 21
    assert check_demo(app)["checked_media_paths"] == 192
    from app.services.admin_service import serialize_admin_video
    from app.services.learning_service import list_joined_courses
    with app.app_context():
        for task in ("retry", "pending", "processing"):
            assert serialize_admin_video(db.session.get(Video, report["video_tasks"][task]))["retryable"]
        course_progress = {row["id"]: row["learning_progress"] for row in list_joined_courses(report["accounts"]["defense_student01"]["id"])}
        assert course_progress[report["courses"]["database"]] == 100
        assert course_progress[report["courses"]["python"]] == 0
        assert course_progress[report["courses"]["c"]] == 51.25
        assert db.session.scalar(db.select(User).where(User.username == "existing_student")).password_hash == old_hash
        main = db.session.get(User, report["accounts"]["defense_student01"]["id"])
        assert check_password_hash(main.password_hash, DEMO_PASSWORD)
        fresh_id = report["accounts"]["defense_new_student"]["id"]
        assert db.session.scalar(db.select(db.func.count()).select_from(CourseStudent).where(CourseStudent.student_id == fresh_id)) == 0
        assert {row.status for row in db.session.scalars(db.select(Course))} == {"DRAFT", "PUBLISHED", "OFFLINE"}
        homework_ids = report["homeworks"]["c"]
        main_statuses = [db.session.scalar(db.select(HomeworkSubmission).where(HomeworkSubmission.homework_id == identity, HomeworkSubmission.student_id == main.id)) for identity in homework_ids[:4]]
        assert [row.status if row else None for row in main_statuses] == [None, "DRAFT", "SUBMITTED", "GRADED"]
        for exam in db.session.scalars(db.select(Exam)):
            assert exam.published_at is None or exam.published_at >= exam.created_at
            assert sum(question.score for question in exam.questions) == exam.total_score == 100
            for record in exam.records:
                assert sum(answer.score for answer in record.answers) == record.score
                if record.status == "SUBMITTED":
                    assert record.started_at <= record.submit_time
                    assert all(answer.created_at <= record.submit_time for answer in record.answers)
                    assert sum(answer.is_correct for answer in record.answers) == record.correct_count
                    assert record.correct_count + record.wrong_count == len(exam.questions)
        video = db.session.get(Video, report["video_tasks"]["retry"])
        video.error_message = "教师演示操作后的新状态"
        db.session.commit()
        before_counts = {model.__name__:db.session.query(model).count() for model in [User, Course, TeachingClass, Homework, Exam, Video, ExamRecord, ExamAnswer, ExamQuestion]}
    second = seed_demo_data(app)
    assert second["already_exists"] is True
    with app.app_context():
        assert {model.__name__:db.session.query(model).count() for model in [User, Course, TeachingClass, Homework, Exam, Video, ExamRecord, ExamAnswer, ExamQuestion]} == before_counts
        assert db.session.get(Video, report["video_tasks"]["retry"]).error_message == "教师演示操作后的新状态"


def test_demo_seed_rejects_username_collision(app, demo_assets):
    with app.app_context():
        row = User(username="defense_teacher", real_name="已有老师", role="TEACHER", password_hash="existing-hash")
        db.session.add(row)
        db.session.commit()
    with pytest.raises(RuntimeError, match="同名前缀"):
        seed_demo_data(app)
    with app.app_context():
        assert db.session.query(User).count() == 1
        assert db.session.query(Course).count() == 0


def test_demo_seed_rolls_back_and_cleans_only_new_files(app, demo_assets, monkeypatch):
    import scripts.seed_demo as seed_module
    original_copy = seed_module.shutil.copy2
    calls = 0
    def failing_copy(source, target):
        nonlocal calls
        calls += 1
        if calls == 7:
            raise OSError("injected-copy-failure")
        return original_copy(source, target)
    monkeypatch.setattr(seed_module.shutil, "copy2", failing_copy)
    sentinel = app.config["MEDIA_ROOT"] / "course_covers" / "existing-user-cover.png"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"preserve-existing")
    with pytest.raises(OSError, match="injected-copy-failure"):
        seed_demo_data(app)
    with app.app_context():
        assert db.session.query(User).count() == 0
        assert db.session.query(Course).count() == 0
    assert sentinel.read_bytes() == b"preserve-existing"
    assert not list((app.config["MEDIA_ROOT"] / "avatars").glob("defense-*"))
    assert (demo_assets / "c/source.mp4").exists()


@pytest.mark.skipif(os.getenv("RUN_FFMPEG_TEST") != "1", reason="启用真实FFmpeg测试时验证演示恢复链路")
def test_demo_failed_video_recovers_without_affecting_ready_video(app, demo_assets):
    from app.services.video_processing_service import process_video_sync
    source = demo_assets / "c/source.mp4"
    subprocess.run([app.config["FFMPEG_BIN"], "-y", "-f", "lavfi", "-i", "color=c=0x315769:size=320x180:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "3", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)],
                   check=True, capture_output=True, timeout=30)
    metadata_path = demo_assets / "manifest.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["courses"]["c"] = {"duration": 3, "width": 320, "height": 180, "file_size": source.stat().st_size}
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    report = seed_demo_data(app)
    with app.app_context():
        ready = db.session.scalar(db.select(Video).join(Video.chapter).where(Chapter.course_id == report["courses"]["c"]).order_by(Video.id))
        root = app.config["MEDIA_ROOT"]
        ready_paths = [root / ready.original_file, root / ready.hls_path, root / ready.cover]
        before = [path.read_bytes() for path in ready_paths]
        recovered = process_video_sync(report["video_tasks"]["retry"], raise_on_error=True)
        assert recovered.status == "READY" and recovered.process_step == "FINISHED"
        assert recovered.video_codec == "h264" and recovered.audio_codec == "aac"
        assert (root / recovered.hls_path).is_file()
        assert [path.read_bytes() for path in ready_paths] == before
