import json
import subprocess
from pathlib import Path


def probe_video(input_path: Path, ffprobe_bin: str = "ffprobe", timeout: int = 60) -> dict:
    command = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(input_path),
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    return json.loads(result.stdout)
