"""对本地 MySQL、Redis、Celery 和 FFmpeg 做一次可清理的异步链路验收。"""

import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from werkzeug.security import generate_password_hash

from app import create_app
from app.constants import UserRole
from app.extensions import db
from app.models import Chapter, Course, CourseCategory, User
from app.services.course_service import delete_draft_course


def create_sample_video(path: Path, ffmpeg_bin: str) -> None:
    subprocess.run(
        [
            ffmpeg_bin,
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


def main() -> None:
    app = create_app()
    if not app.config["VIDEO_PROCESSING_ASYNC"]:
        raise RuntimeError("请先设置 VIDEO_PROCESSING_ASYNC=true")

    marker = uuid4().hex[:10]
    username = f"verify_{marker}"
    password = "Verify123!"
    created_category_id = None
    teacher_id = None
    course_id = None

    try:
        with app.app_context():
            category = db.session.scalar(db.select(CourseCategory).order_by(CourseCategory.id))
            if category is None:
                category = CourseCategory(name=f"验收分类_{marker}")
                db.session.add(category)
                db.session.flush()
                created_category_id = category.id
            teacher = User(
                username=username,
                password_hash=generate_password_hash(password),
                real_name="异步验收教师",
                teacher_no=f"V{marker}",
                role=UserRole.TEACHER.value,
            )
            db.session.add(teacher)
            db.session.flush()
            course = Course(teacher_id=teacher.id, category_id=category.id, name=f"异步验收_{marker}")
            db.session.add(course)
            db.session.flush()
            chapter = Chapter(course_id=course.id, title="验收章节")
            db.session.add(chapter)
            db.session.commit()
            teacher_id = teacher.id
            course_id = course.id
            chapter_id = chapter.id

        client = app.test_client()
        login = client.post("/api/auth/login", json={"account": username, "password": password})
        if login.status_code != 200:
            raise RuntimeError(f"验收账号登录失败：{login.get_json()}")
        token = login.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        with tempfile.TemporaryDirectory(prefix="bs_hfn_async_") as temp_dir:
            source = Path(temp_dir) / "异步验收.mp4"
            create_sample_video(source, app.config["FFMPEG_BIN"])
            with source.open("rb") as handle:
                uploaded = client.post(
                    "/api/videos/upload",
                    headers=headers,
                    data={
                        "chapter_id": str(chapter_id),
                        "title": "异步验收视频",
                        "video_file": (handle, source.name),
                    },
                    content_type="multipart/form-data",
                )

        if uploaded.status_code != 202:
            raise RuntimeError(f"异步上传未成功入队：{uploaded.get_json()}")
        video_id = uploaded.get_json()["data"]["id"]
        print(f"queued video_id={video_id}")

        deadline = time.monotonic() + 180
        last_state = None
        failed_observations = 0
        while time.monotonic() < deadline:
            response = client.get(f"/api/videos/{video_id}/status", headers=headers)
            if response.status_code != 200:
                raise RuntimeError(f"状态查询失败：{response.get_json()}")
            video = response.get_json()["data"]
            state = (video["status"], video["process_step"])
            if state != last_state:
                print(f"status={state[0]} step={state[1]}")
                last_state = state
            if video["status"] == "READY":
                print("async-video-check=passed")
                return
            if video["status"] == "FAILED":
                failed_observations += 1
                if failed_observations >= 2:
                    raise RuntimeError(f"异步处理失败：{video['error_message']}")
            else:
                failed_observations = 0
            time.sleep(1)
        raise TimeoutError("异步视频处理在180秒内未完成")
    finally:
        with app.app_context():
            if course_id and teacher_id and db.session.get(Course, course_id):
                delete_draft_course(course_id, teacher_id)
            if teacher_id:
                teacher = db.session.get(User, teacher_id)
                if teacher:
                    db.session.delete(teacher)
                    db.session.commit()
            if created_category_id:
                category = db.session.get(CourseCategory, created_category_id)
                if category:
                    db.session.delete(category)
                    db.session.commit()


if __name__ == "__main__":
    main()
