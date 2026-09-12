import subprocess
from fractions import Fraction
from pathlib import Path

from flask import current_app
from sqlalchemy.orm import joinedload

from app.constants import CourseStatus, VideoStatus
from app.extensions import db
from app.models import Chapter, Video
from .ffmpeg_service import generate_cover, generate_hls, transcode_video
from .ffprobe_service import probe_video
from .file_service import clear_generated_video_files, remove_file, save_original_video


class VideoNotFound(ValueError):
    pass


class VideoPermissionDenied(PermissionError):
    pass


class VideoProcessingError(RuntimeError):
    pass


def create_video(file, teacher_id: int, data: dict) -> Video:
    chapter = db.session.scalar(
        db.select(Chapter).options(joinedload(Chapter.course)).where(Chapter.id == data["chapter_id"])
    )
    if chapter is None:
        raise VideoNotFound("章节不存在")
    if chapter.course.teacher_id != teacher_id:
        raise VideoPermissionDenied("不能向其他教师的课程上传视频")
    if chapter.course.status != CourseStatus.DRAFT.value:
        raise ValueError("只有草稿课程可以上传视频")

    media_root = Path(current_app.config["MEDIA_ROOT"])
    original_path, original_name = save_original_video(file, media_root / "videos" / "original")
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
    return video


def create_and_process_video(file, teacher_id: int, data: dict) -> Video:
    video = create_video(file, teacher_id, data)
    return process_video_sync(video.id)


def process_video_sync(video_id: int, *, raise_on_error: bool = False) -> Video:
    video = db.session.get(Video, video_id)
    if video is None:
        raise VideoNotFound("视频不存在")

    media_root = Path(current_app.config["MEDIA_ROOT"])
    processed_path = media_root / "videos" / "processed" / str(video.id) / "video.mp4"
    hls_dir = media_root / "videos" / "hls" / str(video.id)
    cover_path = media_root / "videos" / "covers" / f"{video.id}.jpg"

    try:
        clear_generated_video_files(media_root, video.id)
        if not video.original_file:
            raise FileNotFoundError("视频原始文件路径为空")
        original_path = media_root / video.original_file
        if not original_path.is_file():
            raise FileNotFoundError("视频原始文件不存在")

        video.processed_file = None
        video.hls_path = None
        video.cover = None
        _set_step(video, "PROBING")
        metadata = probe_video(original_path, current_app.config["FFPROBE_BIN"])
        _apply_metadata(video, metadata, original_path)

        _set_step(video, "TRANSCODING")
        transcode_video(original_path, processed_path, current_app.config["FFMPEG_BIN"])
        video.processed_file = _relative(processed_path, media_root)

        _set_step(video, "HLS")
        playlist = generate_hls(processed_path, hls_dir, current_app.config["FFMPEG_BIN"])
        video.hls_path = _relative(playlist, media_root)

        _set_step(video, "COVER")
        generate_cover(processed_path, cover_path, current_app.config["FFMPEG_BIN"])
        video.cover = _relative(cover_path, media_root)

        video.status = VideoStatus.READY.value
        video.process_step = "FINISHED"
        video.error_message = None
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
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
    video.status = VideoStatus.FAILED.value
    video.process_step = process_step or video.process_step
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


def _set_step(video: Video, step: str) -> None:
    video.status = VideoStatus.PROCESSING.value
    video.process_step = step
    db.session.commit()


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
