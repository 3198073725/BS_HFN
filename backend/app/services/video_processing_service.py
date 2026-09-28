import subprocess
import uuid
from fractions import Fraction
from pathlib import Path

from flask import current_app
from sqlalchemy.orm import joinedload

from app.constants import CourseStatus, VideoStatus
from app.extensions import db
from app.models import Chapter, Video
from .ffmpeg_service import generate_cover, generate_hls, transcode_video
from .ffprobe_service import probe_video
from .file_service import (
    ALLOWED_VIDEO_EXTENSIONS,
    UploadCancelledError,
    clear_generated_video_files,
    cleanup_stale_video_upload_markers,
    is_video_upload_cancelled,
    mark_video_upload_cancelled,
    remove_all_video_files,
    remove_file,
    save_original_video,
)


class VideoNotFound(ValueError):
    pass


class VideoPermissionDenied(PermissionError):
    pass


class VideoProcessingError(RuntimeError):
    pass


class VideoProcessingCancelled(RuntimeError):
    pass


class VideoFileValidationError(ValueError):
    pass


class VideoStateError(ValueError):
    pass


class VideoUploadCancelled(ValueError):
    pass


def create_video(file, teacher_id: int, data: dict) -> Video:
    chapter = db.session.scalar(
        db.select(Chapter).options(joinedload(Chapter.course)).where(Chapter.id == data["chapter_id"])
    )
    if chapter is None:
        raise VideoNotFound("章节不存在")
    if chapter.course.teacher_id != teacher_id:
        raise VideoPermissionDenied("不能向其他教师的课程上传视频")
    if chapter.course.status not in {item.value for item in CourseStatus}:
        raise ValueError("课程状态异常，暂时不能上传视频")

    media_root = Path(current_app.config["MEDIA_ROOT"])
    upload_token = data.get("upload_token")
    cleanup_stale_video_upload_markers(media_root)
    if is_video_upload_cancelled(media_root, upload_token):
        raise VideoUploadCancelled("视频上传已取消")
    try:
        original_path, original_name = save_original_video(
            file,
            media_root / "videos" / "original",
            storage_stem=upload_token,
            cancel_check=(
                lambda: is_video_upload_cancelled(media_root, upload_token)
                if upload_token else None
            ),
        )
    except UploadCancelledError as exc:
        raise VideoUploadCancelled(str(exc)) from exc
    except ValueError as exc:
        raise VideoFileValidationError(str(exc)) from exc
    video = Video(
        chapter_id=chapter.id,
        title=data["title"],
        description=data.get("description"),
        original_name=original_name,
        original_file=_relative(original_path, media_root),
        file_size=original_path.stat().st_size,
        sort_order=data.get("sort_order", 0),
        status=VideoStatus.PENDING.value,
    )
    db.session.add(video)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        remove_file(original_path)
        raise
    if is_video_upload_cancelled(media_root, upload_token):
        db.session.delete(video)
        db.session.commit()
        remove_file(original_path)
        raise VideoUploadCancelled("视频上传已取消")
    return video


def cancel_pending_video_upload(upload_token: str, teacher_id: int) -> bool:
    """Cancel a browser upload before or after its Video row is committed."""
    media_root = Path(current_app.config["MEDIA_ROOT"])
    mark_video_upload_cancelled(media_root, upload_token)
    possible_files = [
        f"videos/original/{upload_token}{suffix}"
        for suffix in ALLOWED_VIDEO_EXTENSIONS
    ]
    video = db.session.scalar(
        db.select(Video)
        .options(joinedload(Video.chapter).joinedload(Chapter.course))
        .where(Video.original_file.in_(possible_files))
    )
    if video is None:
        return False
    if video.chapter.course.teacher_id != teacher_id:
        raise VideoPermissionDenied("不能取消其他教师的视频上传")
    delete_teacher_video(video.id, teacher_id)
    return True


def create_and_process_video(file, teacher_id: int, data: dict) -> Video:
    video = create_video(file, teacher_id, data)
    return process_video_sync(video.id)


def enqueue_video_processing(video_id: int, upload_token: str | None = None) -> Video:
    media_root = Path(current_app.config["MEDIA_ROOT"])
    if is_video_upload_cancelled(media_root, upload_token):
        video = db.session.get(Video, video_id)
        if video is not None:
            original_file = video.original_file
            db.session.delete(video)
            db.session.commit()
            remove_all_video_files(media_root, video_id, original_file)
        raise VideoUploadCancelled("视频上传已取消")

    task_id = uuid.uuid4().hex
    updated = db.session.execute(
        db.update(Video)
        .where(
            Video.id == video_id,
            Video.status == VideoStatus.PENDING.value,
            Video.task_id.is_(None),
        )
        .values(task_id=task_id, process_step="QUEUED")
    )
    db.session.commit()
    if updated.rowcount != 1:
        if is_video_upload_cancelled(media_root, upload_token):
            raise VideoUploadCancelled("视频上传已取消")
        status, _current_task_id = _processing_state(video_id)
        if status is None:
            raise VideoNotFound("视频不存在")
        raise VideoStateError("只有尚未投递的等待视频可以加入转码队列")
    db.session.expire_all()
    video = db.session.get(Video, video_id)
    if video is None:
        raise VideoUploadCancelled("视频上传已取消")

    from app.tasks.video_tasks import process_video

    process_video.apply_async(args=[video.id, task_id], task_id=task_id)
    return video


def process_video_sync(
    video_id: int,
    *,
    raise_on_error: bool = False,
    expected_task_id: str | None = None,
) -> Video:
    video = db.session.get(Video, video_id)
    if video is None:
        raise VideoNotFound("视频不存在")

    media_root = Path(current_app.config["MEDIA_ROOT"])
    processed_path = media_root / "videos" / "processed" / str(video.id) / "video.mp4"
    hls_dir = media_root / "videos" / "hls" / str(video.id)
    cover_path = media_root / "videos" / "covers" / f"{video.id}.jpg"

    try:
        _assert_processing_current(video.id, expected_task_id)
        clear_generated_video_files(media_root, video.id)
        if not video.original_file:
            raise FileNotFoundError("视频原始文件路径为空")
        original_path = media_root / video.original_file
        if not original_path.is_file():
            raise FileNotFoundError("视频原始文件不存在")

        video.processed_file = None
        video.hls_path = None
        video.cover = None
        _set_step(video, "PROBING", expected_task_id)
        metadata = probe_video(original_path, current_app.config["FFPROBE_BIN"])
        _apply_metadata(video, metadata, original_path)

        _set_step(video, "TRANSCODING", expected_task_id)
        transcode_video(
            original_path,
            processed_path,
            current_app.config["FFMPEG_BIN"],
            cancel_check=lambda: _assert_processing_current(video.id, expected_task_id),
        )
        _assert_processing_current(video.id, expected_task_id)
        video.processed_file = _relative(processed_path, media_root)

        _set_step(video, "HLS", expected_task_id)
        playlist = generate_hls(
            processed_path,
            hls_dir,
            current_app.config["FFMPEG_BIN"],
            cancel_check=lambda: _assert_processing_current(video.id, expected_task_id),
        )
        _assert_processing_current(video.id, expected_task_id)
        video.hls_path = _relative(playlist, media_root)

        _set_step(video, "COVER", expected_task_id)
        generate_cover(
            processed_path,
            cover_path,
            current_app.config["FFMPEG_BIN"],
            cancel_check=lambda: _assert_processing_current(video.id, expected_task_id),
        )
        _assert_processing_current(video.id, expected_task_id)
        video.cover = _relative(cover_path, media_root)

        video.status = VideoStatus.READY.value
        video.process_step = "FINISHED"
        video.task_id = None
        video.error_message = None
        db.session.commit()
    except VideoProcessingCancelled:
        db.session.rollback()
        status, _task_id = _processing_state(video_id)
        if status in {None, VideoStatus.CANCELLED.value}:
            try:
                clear_generated_video_files(media_root, video_id)
            except (OSError, ValueError):
                current_app.logger.exception("视频 %s 的终止残留文件清理失败", video_id)
        db.session.expire_all()
        return db.session.get(Video, video_id)
    except Exception as exc:
        db.session.rollback()
        status, task_id = _processing_state(video_id)
        if status in {None, VideoStatus.CANCELLED.value}:
            try:
                clear_generated_video_files(media_root, video_id)
            except (OSError, ValueError):
                current_app.logger.exception("视频 %s 的终止残留文件清理失败", video_id)
            db.session.expire_all()
            return db.session.get(Video, video_id)
        if expected_task_id is not None and task_id != expected_task_id:
            db.session.expire_all()
            return db.session.get(Video, video_id)
        try:
            clear_generated_video_files(media_root, video_id)
        except (OSError, ValueError):
            current_app.logger.exception("视频 %s 的失败残留文件清理失败", video_id)
        message = _processing_error_message(exc)
        video = mark_video_failed(video_id, message)
        if raise_on_error:
            raise VideoProcessingError(message) from exc
    return video


def mark_video_failed(video_id: int, message: str, process_step: str | None = None) -> Video:
    video = db.session.get(Video, video_id)
    if video is None:
        raise VideoNotFound("视频不存在")
    if video.status == VideoStatus.CANCELLED.value:
        return video
    video.status = VideoStatus.FAILED.value
    video.process_step = process_step or video.process_step
    video.task_id = None
    video.error_message = message[:2000]
    video.processed_file = None
    video.hls_path = None
    video.cover = None
    db.session.commit()
    return video


def mark_video_retry_pending(video_id: int, message: str) -> Video:
    video = db.session.get(Video, video_id)
    if video is None:
        raise VideoNotFound("视频不存在")
    if video.status == VideoStatus.CANCELLED.value:
        return video
    video.status = VideoStatus.PENDING.value
    video.process_step = None
    video.error_message = message[:2000]
    db.session.commit()
    return video


def get_visible_video(video_id: int, viewer_id: int | None, viewer_role: str | None) -> Video:
    video = db.session.scalar(
        db.select(Video)
        .options(joinedload(Video.chapter).joinedload(Chapter.course))
        .where(Video.id == video_id)
    )
    if video is None:
        raise VideoNotFound("视频不存在")
    course = video.chapter.course
    can_manage = viewer_role == "ADMIN" or (viewer_role == "TEACHER" and course.teacher_id == viewer_id)
    if (
        course.status != CourseStatus.PUBLISHED.value
        or video.status != VideoStatus.READY.value
    ) and not can_manage:
        raise VideoNotFound("视频不存在")
    return video


def update_video(video_id: int, teacher_id: int, data: dict) -> Video:
    video = _owned_video(video_id, teacher_id)
    for field, value in data.items():
        setattr(video, field, value)
    db.session.commit()
    return video


def prepare_teacher_retry(video_id: int, teacher_id: int) -> Video:
    video = _owned_video(video_id, teacher_id)
    if video.status not in {VideoStatus.FAILED.value, VideoStatus.CANCELLED.value}:
        raise VideoStateError("只有处理失败或已终止的视频可以重新转码")
    original_path = _original_path(video)
    if original_path is None or not original_path.is_file():
        raise VideoStateError("原始视频文件已丢失，无法重新转码")
    try:
        clear_generated_video_files(
            Path(current_app.config["MEDIA_ROOT"]),
            video.id,
            retry_timeout=3,
        )
    except PermissionError as exc:
        raise VideoStateError("旧转码进程尚未完全退出，请稍后再试") from exc
    video.status = VideoStatus.PENDING.value
    video.process_step = "QUEUED"
    video.task_id = None
    video.error_message = None
    video.processed_file = None
    video.hls_path = None
    video.cover = None
    db.session.commit()
    return video


def delete_teacher_video(video_id: int, teacher_id: int) -> bool:
    video = _owned_video(video_id, teacher_id)
    was_processing = video.status in {
        VideoStatus.UPLOADING.value,
        VideoStatus.PENDING.value,
        VideoStatus.PROCESSING.value,
    }
    # Published courses may accept newly uploaded videos, but an unfinished
    # video is never visible to students.  Its owner must therefore still be
    # able to cancel/remove it without taking the whole course offline.  READY
    # content remains protected by the normal offline-first rule.
    removable_while_published = was_processing or video.status in {
        VideoStatus.FAILED.value,
        VideoStatus.CANCELLED.value,
    }
    if not removable_while_published:
        _ensure_course_content_change_allowed(video)
    task_id = video.task_id if was_processing else None
    if was_processing:
        # Commit the terminal state before revoking/deleting so a worker that is
        # between FFmpeg stages cannot publish READY after the teacher deletes it.
        video.status = VideoStatus.CANCELLED.value
        video.process_step = "CANCELLED"
        video.task_id = None
        video.error_message = "教师删除视频并终止转码任务"
        db.session.commit()
    original_file = video.original_file
    db.session.delete(video)
    db.session.commit()
    # The row deletion itself is also a worker-visible terminal signal.  Do
    # this before the best-effort broker command so a temporarily unavailable
    # broker cannot leave a deleted video visible forever.
    if was_processing:
        revoke_video_processing_task(task_id)
    try:
        remove_all_video_files(
            Path(current_app.config["MEDIA_ROOT"]),
            video_id,
            original_file,
            retry_timeout=5 if was_processing else 0,
        )
    except (OSError, ValueError):
        current_app.logger.exception("教师删除视频 %s 后清理媒体文件失败", video_id)
    return was_processing


def replace_video(file, video_id: int, teacher_id: int, data: dict) -> Video:
    video = _owned_video(video_id, teacher_id)
    _ensure_content_change_allowed(video)
    media_root = Path(current_app.config["MEDIA_ROOT"])
    try:
        original_path, original_name = save_original_video(
            file,
            media_root / "videos" / "original",
        )
    except ValueError as exc:
        raise VideoFileValidationError(str(exc)) from exc

    old_original_file = video.original_file
    replacement = Video(
        chapter_id=video.chapter_id,
        title=data["title"],
        description=data.get("description"),
        original_name=original_name,
        original_file=_relative(original_path, media_root),
        file_size=original_path.stat().st_size,
        sort_order=data.get("sort_order", 0),
        status=VideoStatus.PENDING.value,
    )
    db.session.add(replacement)
    db.session.delete(video)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        remove_file(original_path)
        raise
    try:
        remove_all_video_files(media_root, video_id, old_original_file)
    except (OSError, ValueError):
        current_app.logger.exception("替换视频 %s 后清理旧媒体文件失败", video_id)
    return replacement


def _set_step(video: Video, step: str, expected_task_id: str | None = None) -> None:
    _assert_processing_current(video.id, expected_task_id)
    video.status = VideoStatus.PROCESSING.value
    video.process_step = step
    db.session.commit()


def _assert_processing_current(video_id: int, expected_task_id: str | None = None) -> None:
    status, task_id = _processing_state(video_id)
    if status is None:
        raise VideoProcessingCancelled("视频任务已不存在")
    if status == VideoStatus.CANCELLED.value:
        raise VideoProcessingCancelled("视频转码任务已终止")
    if expected_task_id is not None and task_id != expected_task_id:
        raise VideoProcessingCancelled("视频转码任务已被替换")


def _processing_state(video_id: int) -> tuple[str | None, str | None]:
    # Do not reuse the long-lived ORM session owned by the Celery task here.
    # MySQL's default REPEATABLE READ isolation can otherwise keep returning
    # the snapshot from before an administrator/teacher cancelled the task.
    # A short independent transaction observes the latest committed state on
    # every FFmpeg polling checkpoint.
    with db.engine.connect() as connection:
        state = connection.execute(
            db.select(Video.status, Video.task_id).where(Video.id == video_id)
        ).one_or_none()
    if state is None:
        return None, None
    return state[0], state[1]


def _owned_video(video_id: int, teacher_id: int) -> Video:
    video = db.session.scalar(
        db.select(Video)
        .options(joinedload(Video.chapter).joinedload(Chapter.course))
        .where(Video.id == video_id)
    )
    if video is None:
        raise VideoNotFound("视频不存在")
    if video.chapter.course.teacher_id != teacher_id:
        raise VideoPermissionDenied("不能管理其他教师的视频")
    return video


def _ensure_content_change_allowed(video: Video) -> None:
    _ensure_course_content_change_allowed(video)
    if video.status in {VideoStatus.PENDING.value, VideoStatus.PROCESSING.value}:
        raise VideoStateError("视频正在处理，暂时不能删除或替换")


def _ensure_course_content_change_allowed(video: Video) -> None:
    if video.chapter.course.status not in {
        CourseStatus.DRAFT.value,
        CourseStatus.OFFLINE.value,
    }:
        raise VideoStateError("课程发布期间不能删除或替换视频，请先下线课程")


def revoke_video_processing_task(task_id: str | None) -> bool:
    """Best-effort revoke for a queued/running Celery video task."""
    if not task_id:
        return False
    celery = current_app.extensions.get("celery")
    if celery is None:
        return False
    try:
        celery.control.revoke(
            task_id,
            terminate=True,
            signal="SIGTERM",
            reply=False,
            timeout=1,
        )
    except Exception:
        current_app.logger.exception("撤销视频转码任务 %s 失败", task_id)
        return False
    return True


def _original_path(video: Video) -> Path | None:
    if not video.original_file:
        return None
    media_root = Path(current_app.config["MEDIA_ROOT"]).resolve()
    candidate = (media_root / video.original_file).resolve()
    if candidate == media_root or not candidate.is_relative_to(media_root):
        return None
    return candidate


def _apply_metadata(video: Video, metadata: dict, original_path: Path) -> None:
    streams = metadata.get("streams", [])
    video_stream = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), {})
    format_data = metadata.get("format", {})
    video.duration = _number(format_data.get("duration"))
    video.width = video_stream.get("width")
    video.height = video_stream.get("height")
    video.video_codec = video_stream.get("codec_name")
    video.audio_codec = audio_stream.get("codec_name")
    video.bitrate = int(format_data["bit_rate"]) if format_data.get("bit_rate") else None
    video.frame_rate = _frame_rate(video_stream.get("avg_frame_rate"))
    video.file_size = original_path.stat().st_size


def _frame_rate(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    return float(Fraction(value))


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _relative(path: Path, media_root: Path) -> str:
    return path.resolve().relative_to(media_root.resolve()).as_posix()


def _processing_error_message(exc: Exception) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        detail = (exc.stderr or exc.stdout or "").strip()
        if detail:
            return f"FFmpeg/ffprobe 执行失败：{detail[-1800:]}"
    if isinstance(exc, subprocess.TimeoutExpired):
        return f"FFmpeg/ffprobe 执行超时：{exc.timeout} 秒"
    return f"{type(exc).__name__}: {exc}"
