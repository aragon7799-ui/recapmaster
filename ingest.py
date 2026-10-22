from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..config import settings
from .media import ffprobe_json, media_summary, run_command


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}


def is_youtube_url(url: str) -> bool:
    try:
        return (urlparse(url).hostname or "").lower() in YOUTUBE_HOSTS
    except ValueError:
        return False


def validate_source(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        raise ValueError("The source file is missing or empty.")
    if path.stat().st_size > settings.max_upload_bytes:
        raise ValueError(f"The source exceeds the configured {settings.max_upload_bytes // (1024 * 1024)} MB limit.")
    summary = media_summary(ffprobe_json(path))
    if summary["duration"] <= 0 or summary["width"] <= 0 or summary["height"] <= 0:
        raise ValueError("The source has no readable video stream or duration.")
    if summary["duration"] > settings.max_source_duration_seconds:
        raise ValueError(f"The source is longer than the configured {settings.max_source_duration_seconds // 3600} hour limit.")
    return summary


def download_source(url: str, target_dir: Path) -> tuple[Path, dict]:
    target_dir.mkdir(parents=True, exist_ok=True)
    if is_youtube_url(url):
        output_template = str(target_dir / "source.%(ext)s")
        run_command([
            settings.ytdlp_bin, "--no-playlist", "--restrict-filenames", "-f", "bv*+ba/b",
            "--merge-output-format", "mp4", "-o", output_template, url,
        ], timeout=1800)
        candidates = sorted(target_dir.glob("source.*"), key=lambda item: item.stat().st_mtime, reverse=True)
        candidates = [item for item in candidates if item.suffix.lower() not in {".part", ".ytdl"}]
        if not candidates:
            raise RuntimeError("yt-dlp completed without producing a media file.")
        path = candidates[0]
    else:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Source URL must use http or https.")
        path = target_dir / "source.mp4"
        with httpx.Client(follow_redirects=True, timeout=180) as client:
            with client.stream("GET", url, headers={"User-Agent": "RecapMasterAI/1.0"}) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type.lower():
                    raise ValueError("The URL returned an HTML page, not a direct video file. Use a direct MP4 URL or upload the file.")
                with path.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
                        if handle.tell() > settings.max_upload_bytes:
                            raise ValueError("The downloaded source exceeds the configured size limit.")
    return path, validate_source(path)
