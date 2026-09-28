import shutil
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from werkzeug.datastructures import FileStorage


ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
ALLOWED_COURSE_COVER_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}
ALLOWED_HOMEWORK_EXTENSIONS = {
    ".7z",
    ".doc",
    ".docx",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".txt",
    ".xls",
    ".xlsx",
    ".zip",
}


class UploadCancelledError(ValueError):
    pass


def save_original_video(
    file: FileStorage,
    target_dir: Path,
    *,
    storage_stem: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[Path, str]:
    original_name = Path(str(file.filename or "").replace("\\", "/")).name.strip()
    suffix = Path(original_name).suffix.lower()
    if not original_name or suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValueError("不支持的视频格式")
    if len(original_name) > 255:
        raise ValueError("视频文件名不能超过255位")

    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{storage_stem or uuid4().hex}{suffix}"
    try:
        size = 0
        with target.open("xb") as output:
            while chunk := file.stream.read(1024 * 1024):
                if cancel_check is not None and cancel_check():
                    raise UploadCancelledError("视频上传已取消")
                output.write(chunk)
                size += len(chunk)
        if cancel_check is not None and cancel_check():
            raise UploadCancelledError("视频上传已取消")
        if size == 0:
            raise ValueError("视频文件不能为空")
    except Exception:
        remove_file(target)
        raise
    return target, original_name


def mark_video_upload_cancelled(media_root: Path, upload_token: str) -> None:
    marker = _video_upload_cancel_marker(media_root, upload_token)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch(exist_ok=True)


def is_video_upload_cancelled(media_root: Path, upload_token: str | None) -> bool:
    return bool(upload_token and _video_upload_cancel_marker(media_root, upload_token).is_file())


def clear_video_upload_cancel_marker(media_root: Path, upload_token: str | None) -> None:
    if upload_token:
        remove_file(_video_upload_cancel_marker(media_root, upload_token))


def cleanup_stale_video_upload_markers(media_root: Path, max_age_seconds: int = 86400) -> None:
    marker_dir = media_root / "videos" / "upload_control"
    if not marker_dir.is_dir():
        return
    cutoff = time.time() - max_age_seconds
    for marker in marker_dir.glob("*.cancel"):
        try:
            if marker.stat().st_mtime < cutoff:
                marker.unlink()
        except FileNotFoundError:
            continue


def _video_upload_cancel_marker(media_root: Path, upload_token: str) -> Path:
    return media_root / "videos" / "upload_control" / f"{upload_token}.cancel"


def remove_file(path: Path) -> None:
    if path.is_file():
        path.unlink()


def save_homework_attachment(
    file: FileStorage,
    target_dir: Path,
    maximum_bytes: int,
) -> Path:
    original_name = Path(str(file.filename or "").replace("\\", "/")).name.strip()
    suffix = Path(original_name).suffix.lower()
    if not original_name or suffix not in ALLOWED_HOMEWORK_EXTENSIONS:
        raise ValueError("不支持的附件格式")
    if len(original_name) > 255:
        raise ValueError("附件文件名不能超过255位")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4().hex}{suffix}"
    try:
        size = 0
        with target.open("xb") as output:
            while chunk := file.stream.read(64 * 1024):
                size += len(chunk)
                if size > maximum_bytes:
                    raise ValueError(f"附件不能超过{maximum_bytes // 1024 // 1024}MB")
                output.write(chunk)
        if size == 0:
            raise ValueError("附件文件不能为空")
    except Exception:
        remove_file(target)
        raise
    return target


def save_course_cover(file: FileStorage, target_dir: Path, maximum_bytes: int) -> Path:
    original_name = Path(str(file.filename or "").replace("\\", "/")).name.strip()
    suffix = Path(original_name).suffix.lower()
    if not original_name or suffix not in ALLOWED_COURSE_COVER_EXTENSIONS:
        raise ValueError("课程封面仅支持 JPG、PNG 或 WebP 格式")

    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4().hex}{suffix}"
    size = 0
    try:
        try:
            file.stream.seek(0)
        except (AttributeError, OSError):
            pass
        with target.open("xb") as output:
            while chunk := file.stream.read(64 * 1024):
                size += len(chunk)
                if size > maximum_bytes:
                    raise ValueError(f"课程封面不能超过{maximum_bytes // 1024 // 1024}MB")
                output.write(chunk)
        if size == 0:
            raise ValueError("课程封面不能为空")
        with target.open("rb") as saved_file:
            header = saved_file.read(16)
        if not _valid_image_signature(suffix, header):
            raise ValueError("课程封面文件内容与图片格式不匹配")
    except Exception:
        remove_file(target)
        raise
    return target


def save_profile_avatar(file: FileStorage, target_dir: Path, maximum_bytes: int) -> Path:
    original_name = Path(str(file.filename or "").replace("\\", "/")).name.strip()
    suffix = Path(original_name).suffix.lower()
    if not original_name or suffix not in ALLOWED_COURSE_COVER_EXTENSIONS:
        raise ValueError("头像仅支持 JPG、PNG 或 WebP 格式")

    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4().hex}{suffix}"
    size = 0
    try:
        try:
            file.stream.seek(0)
        except (AttributeError, OSError):
            pass
        with target.open("xb") as output:
            while chunk := file.stream.read(64 * 1024):
                size += len(chunk)
                if size > maximum_bytes:
                    raise ValueError(f"头像不能超过{maximum_bytes // 1024 // 1024}MB")
                output.write(chunk)
        if size == 0:
            raise ValueError("头像文件不能为空")
        with target.open("rb") as saved_file:
            header = saved_file.read(16)
        if not _valid_image_signature(suffix, header):
            raise ValueError("头像文件内容与图片格式不匹配")
    except Exception:
        remove_file(target)
        raise
    return target


def remove_media_file(media_root: Path, relative_path: str | None) -> None:
    if not relative_path:
        return
    resolved_root = media_root.resolve()
    target = (media_root / relative_path).resolve()
    if target == resolved_root or not target.is_relative_to(resolved_root):
        raise ValueError("拒绝删除媒体目录之外的文件")
    remove_file(target)


def clear_generated_video_files(
    media_root: Path,
    video_id: int,
    *,
    retry_timeout: float = 0,
    retry_interval: float = 0.1,
) -> None:
    """Remove generated media, briefly waiting for a cancelled FFmpeg process.

    Windows does not allow deleting ``video.mp4`` while FFmpeg still has the
    file open.  Cancellation is database-backed and the worker checks it at
    sub-second intervals, so lifecycle actions may opt into a short retry
    window instead of leaking a raw ``WinError 32`` response.
    """
    deadline = time.monotonic() + max(0, retry_timeout)
    while True:
        try:
            for directory in (
                media_root / "videos" / "processed" / str(video_id),
                media_root / "videos" / "hls" / str(video_id),
            ):
                _remove_tree_within(directory, media_root)
            remove_file(media_root / "videos" / "covers" / f"{video_id}.jpg")
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(max(0.01, retry_interval))


def remove_all_video_files(
    media_root: Path,
    video_id: int,
    original_file: str | None,
    *,
    retry_timeout: float = 0,
) -> None:
    clear_generated_video_files(
        media_root,
        video_id,
        retry_timeout=retry_timeout,
    )
    if not original_file:
        return
    original_path = (media_root / original_file).resolve()
    resolved_root = media_root.resolve()
    if not original_path.is_relative_to(resolved_root):
        raise ValueError("拒绝删除媒体目录之外的文件")
    remove_file(original_path)


def clear_homework_files(media_root: Path, homework_id: int) -> None:
    _remove_tree_within(media_root / "homework" / str(homework_id), media_root)


def clear_exam_files(media_root: Path, exam_id: int) -> None:
    _remove_tree_within(media_root / "exams" / str(exam_id), media_root)


def _valid_image_signature(suffix: str, header: bytes) -> bool:
    if suffix in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix == ".webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return False


def _remove_tree_within(path: Path, allowed_root: Path) -> None:
    resolved_root = allowed_root.resolve()
    resolved_path = path.resolve()
    if resolved_path == resolved_root or not resolved_path.is_relative_to(resolved_root):
        raise ValueError("拒绝清理媒体目录之外的路径")
    if resolved_path.is_dir():
        shutil.rmtree(resolved_path)
