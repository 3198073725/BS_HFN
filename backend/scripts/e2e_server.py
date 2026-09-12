import os
import shutil
import subprocess
from pathlib import Path

from flask import send_from_directory
from werkzeug.security import generate_password_hash

from app import create_app
from app.constants import CourseStatus, UserRole, VideoStatus
from app.datetime_utils import utc_now
from app.extensions import db
from app.models import (
    Chapter,
    Course,
    CourseCategory,
    CourseStudent,
    Notification,
    TeachingClass,
    TeachingClassStudent,
    User,
    Video,
)


E2E_PASSWORD = "E2ePassword123!"
E2E_USERS = (
    {
        "username": "e2e_student",
        "real_name": "端测学生",
        "role": UserRole.STUDENT.value,
        "student_no": "E2ES001",
    },
    {
        "username": "e2e_teacher",
        "real_name": "端测教师",
        "role": UserRole.TEACHER.value,
        "teacher_no": "E2ET001",
    },
    {
        "username": "e2e_admin",
        "real_name": "端测管理员",
        "role": UserRole.ADMIN.value,
    },
    {
        "username": "e2e_empty_student",
        "real_name": "空数据学生",
        "role": UserRole.STUDENT.value,
        "student_no": "E2ES002",
    },
)


def _create_hls_fixture(app) -> str:
    media_root = Path(app.config["MEDIA_ROOT"])
    upload_fixture = media_root / "videos" / "original" / "e2e-upload.mp4"
    hls_directory = media_root / "videos" / "hls" / "e2e"
    if hls_directory.exists():
        shutil.rmtree(hls_directory)
    upload_fixture.parent.mkdir(parents=True, exist_ok=True)
    hls_directory.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            app.config["FFMPEG_BIN"],
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:sample_rate=44100",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(upload_fixture),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    playlist = hls_directory / "index.m3u8"
    segment_pattern = hls_directory / "segment_%03d.ts"
    subprocess.run(
        [
            app.config["FFMPEG_BIN"],
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=44100",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-f",
            "hls",
            "-hls_time",
            "1",
            "-hls_list_size",
            "0",
            "-hls_segment_filename",
            str(segment_pattern),
            str(playlist),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return playlist.relative_to(media_root).as_posix()


def create_e2e_app():
    app = create_app("testing")
    hls_path = _create_hls_fixture(app)
    media_root = Path(app.config["MEDIA_ROOT"])
    failed_original = media_root / "videos" / "original" / "e2e-failed-retry.mp4"
    shutil.copyfile(media_root / "videos" / "original" / "e2e-upload.mp4", failed_original)

    @app.get("/media/<path:filename>")
    def e2e_media_file(filename: str):
        return send_from_directory(app.config["MEDIA_ROOT"], filename)

    with app.app_context():
        db.create_all()
        password_hash = generate_password_hash(E2E_PASSWORD)
        category = CourseCategory(name="端测分类", sort_order=0)
        users = [
            User(password_hash=password_hash, **user_data) for user_data in E2E_USERS
        ]
        db.session.add_all([category, *users])
        db.session.flush()
        student, teacher, _admin, _empty_student = users
        reset_classroom = TeachingClass(
            teacher_id=teacher.id,
            name="端测密码审批班",
            description="用于验证学生密码重置审批流程。",
        )
        db.session.add(reset_classroom)
        db.session.flush()
        db.session.add(
            TeachingClassStudent(class_id=reset_classroom.id, student_id=student.id)
        )
        course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="端测基础课程",
            description="包含由项目内 FFmpeg 生成的浏览器测试视频。",
            status=CourseStatus.PUBLISHED.value,
            published_at=utc_now(),
        )
        db.session.add(course)
        db.session.flush()
        chapter = Chapter(course_id=course.id, title="第一章 HLS 播放验证", sort_order=0)
        db.session.add(chapter)
        db.session.flush()
        video = Video(
            chapter_id=chapter.id,
            title="端测 HLS 视频",
            hls_path=hls_path,
            duration=3,
            width=320,
            height=180,
            video_codec="h264",
            audio_codec="aac",
            status=VideoStatus.READY.value,
            process_step="FINISHED",
        )
        membership = CourseStudent(
            course_id=course.id,
            student_id=student.id,
            status=True,
        )
        welcome_notification = Notification(
            recipient_id=student.id,
            category="SYSTEM",
            title="端到端消息中心验证",
            content="这是一条用于验证消息读取状态的站内通知。",
            link="/learning",
        )
        db.session.add_all([video, membership, welcome_notification])
        long_course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="端测超长课程名称ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789连续字符边界验证",
            description=(
                "用于验证中文与连续英文混排时不会撑破卡片："
                "https://example.invalid/"
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            ),
            status=CourseStatus.PUBLISHED.value,
            published_at=utc_now(),
        )
        upload_course = Course(
            teacher_id=teacher.id,
            category_id=category.id,
            name="端测视频上传草稿",
            description="用于浏览器上传和转码验收。",
            status=CourseStatus.DRAFT.value,
        )
        db.session.add_all([long_course, upload_course])
        db.session.flush()
        upload_chapter = Chapter(
            course_id=upload_course.id,
            title="上传测试章节",
            sort_order=0,
        )
        db.session.add(upload_chapter)
        db.session.flush()
        db.session.add(
            Video(
                chapter_id=upload_chapter.id,
                title="端测失败转码视频",
                original_name="e2e-failed-retry.mp4",
                original_file="videos/original/e2e-failed-retry.mp4",
                file_size=failed_original.stat().st_size,
                status=VideoStatus.FAILED.value,
                process_step="TRANSCODING",
                error_message="端到端模拟：转码进程异常退出",
                sort_order=1,
            )
        )
        db.session.commit()
    return app


if __name__ == "__main__":
    create_e2e_app().run(
        host="127.0.0.1",
        port=int(os.getenv("E2E_BACKEND_PORT", "5100")),
        debug=False,
        use_reloader=False,
        threaded=False,
    )
