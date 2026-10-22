from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Sequence

from ..config import settings


class MediaCommandError(RuntimeError):
    def __init__(self, command: Sequence[str], returncode: int, stderr: str):
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"Command failed ({returncode}): {' '.join(self.command)}\n{stderr[-4000:]}")


def run_command(command: Sequence[str], *, timeout: int | None = None, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(list(command), cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if completed.returncode != 0:
        raise MediaCommandError(command, completed.returncode, completed.stderr)
    return completed


def ffprobe_json(path: str | Path) -> dict:
    completed = run_command([
        settings.ffprobe_bin, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
    ], timeout=120)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"FFprobe returned invalid JSON for {path}: {exc}") from exc


def media_summary(probe: dict) -> dict:
    streams = probe.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    fmt = probe.get("format", {})
    return {
        "duration": float(fmt.get("duration") or video.get("duration") or 0),
        "size_bytes": int(fmt.get("size") or 0),
        "bitrate": int(float(fmt.get("bit_rate") or 0)),
        "format": fmt.get("format_name", ""),
        "video_codec": video.get("codec_name", ""),
        "audio_codec": audio.get("codec_name", ""),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": video.get("r_frame_rate", ""),
        "pixel_format": video.get("pix_fmt", ""),
    }


def safe_filename(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return clean or "recap"


def format_srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        whole += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{whole:02d},{millis:03d}"


def write_srt(path: Path, segments: list[dict]) -> None:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = float(segment.get("start", 0))
        end = max(start + 0.4, float(segment.get("end", start + 1)))
        lines.extend([str(index), f"{format_srt_time(start)} --> {format_srt_time(end)}", text, ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
