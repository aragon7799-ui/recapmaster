from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .media import ffprobe_json, media_summary


def verify_video(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"Output file does not exist or is empty: {path}")
    probe = ffprobe_json(path)
    summary = media_summary(probe)
    required = [summary["duration"], summary["width"], summary["height"], summary["video_codec"]]
    if not all(required):
        raise RuntimeError(f"FFprobe verification returned incomplete media metadata for {path}")
    return summary


def create_zip(files: list[Path], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            if file.exists() and file.stat().st_size > 0:
                archive.write(file, arcname=file.name)
    if destination.stat().st_size == 0:
        raise RuntimeError("ZIP packaging produced an empty file.")
    return destination


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
