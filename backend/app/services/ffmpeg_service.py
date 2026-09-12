import subprocess
from pathlib import Path


def transcode_video(
    input_path: Path,
    output_path: Path,
    ffmpeg_bin: str = "ffmpeg",
    timeout: int = 3600,
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
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    return output_path


def generate_hls(
    input_path: Path,
    output_dir: Path,
    ffmpeg_bin: str = "ffmpeg",
    timeout: int = 3600,
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
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    return playlist


def generate_cover(
    input_path: Path,
    output_path: Path,
    ffmpeg_bin: str = "ffmpeg",
    at_seconds: float = 1.0,
    timeout: int = 120,
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
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    return output_path
