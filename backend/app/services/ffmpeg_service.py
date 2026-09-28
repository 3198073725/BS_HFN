import subprocess
import time
from collections.abc import Callable
from pathlib import Path


CancelCheck = Callable[[], None]


def transcode_video(
    input_path: Path,
    output_path: Path,
    ffmpeg_bin: str = "ffmpeg",
    timeout: int = 3600,
    *,
    cancel_check: CancelCheck | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    _run_command(command, timeout, cancel_check)
    return output_path


def generate_hls(
    input_path: Path,
    output_dir: Path,
    ffmpeg_bin: str = "ffmpeg",
    timeout: int = 3600,
    *,
    cancel_check: CancelCheck | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist = output_dir / "index.m3u8"
    segment_pattern = output_dir / "segment_%05d.ts"
    command = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_filename",
        str(segment_pattern),
        str(playlist),
    ]
    _run_command(command, timeout, cancel_check)
    return playlist


def generate_cover(
    input_path: Path,
    output_path: Path,
    ffmpeg_bin: str = "ffmpeg",
    at_seconds: float = 1.0,
    timeout: int = 120,
    *,
    cancel_check: CancelCheck | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_bin,
        "-y",
        "-ss",
        str(at_seconds),
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        str(output_path),
    ]
    _run_command(command, timeout, cancel_check)
    return output_path


def _run_command(command: list[str], timeout: int, cancel_check: CancelCheck | None) -> None:
    """Run FFmpeg while allowing a database-backed cancellation checkpoint.

    Celery's Windows ``solo`` pool cannot reliably interrupt a running task via
    remote control. Polling here lets a Flask delete/cancel request stop the
    actual FFmpeg child instead of only changing the page state.
    """
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    started_at = time.monotonic()
    try:
        while True:
            if cancel_check is not None:
                cancel_check()
            elapsed = time.monotonic() - started_at
            remaining = timeout - elapsed
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                stdout, stderr = process.communicate(timeout=min(0.5, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        _terminate_process(process)
        raise
    if process.returncode:
        raise subprocess.CalledProcessError(
            process.returncode,
            command,
            output=stdout,
            stderr=stderr,
        )


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
