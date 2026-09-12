import os
from pathlib import Path
import shutil
import subprocess

from flask import send_from_directory
from werkzeug.security import generate_password_hash

from app import create_app
from app.constants import CourseStatus, UserRole, VideoStatus
from app.datetime_utils import utc_now
from app.extensions import db
from app.models import Chapter, Course, CourseCategory, CourseStudent, User, Video


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
    hls_directory = media_root / "videos" / "hls" / "e2e"
    if hls_directory.exists():
        shutil.rmtree(hls_directory)
    hls_directory.mkdir(parents=True, exist_ok=True)
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
        db.session.add_all([video, membership])
        db.session.add(
            Course(
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
