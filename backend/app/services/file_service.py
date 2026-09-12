import shutil
from pathlib import Path
from uuid import uuid4

from werkzeug.datastructures import FileStorage


ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
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


def save_original_video(file: FileStorage, target_dir: Path) -> tuple[Path, str]:
    original_name = Path(str(file.filename or "").replace("\\", "/")).name.strip()
    suffix = Path(original_name).suffix.lower()
    if not original_name or suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValueError("不支持的视频格式")
    if len(original_name) > 255:
        raise ValueError("视频文件名不能超过255位")

    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4().hex}{suffix}"
    try:
        file.save(target)
        if target.stat().st_size == 0:
            raise ValueError("视频文件不能为空")
    except Exception:
        remove_file(target)
        raise
    return target, original_name


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
        file.save(target)
        size = target.stat().st_size
        if size == 0:
            raise ValueError("附件文件不能为空")
        if size > maximum_bytes:
            raise ValueError(f"附件不能超过{maximum_bytes // 1024 // 1024}MB")
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


def clear_generated_video_files(media_root: Path, video_id: int) -> None:
    for directory in (
        media_root / "videos" / "processed" / str(video_id),
        media_root / "videos" / "hls" / str(video_id),
    ):
        _remove_tree_within(directory, media_root)
    remove_file(media_root / "videos" / "covers" / f"{video_id}.jpg")


def remove_all_video_files(media_root: Path, video_id: int, original_file: str | None) -> None:
    clear_generated_video_files(media_root, video_id)
    if not original_file:
        return
    original_path = (media_root / original_file).resolve()
    resolved_root = media_root.resolve()
    if not original_path.is_relative_to(resolved_root):
        raise ValueError("拒绝删除媒体目录之外的文件")
    remove_file(original_path)


def clear_homework_files(media_root: Path, homework_id: int) -> None:
    _remove_tree_within(media_root / "homework" / str(homework_id), media_root)


def _remove_tree_within(path: Path, allowed_root: Path) -> None:
    resolved_root = allowed_root.resolve()
    resolved_path = path.resolve()
    if resolved_path == resolved_root or not resolved_path.is_relative_to(resolved_root):
        raise ValueError("拒绝清理媒体目录之外的路径")
    if resolved_path.is_dir():
        shutil.rmtree(resolved_path)
