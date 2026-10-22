from __future__ import annotations

from pathlib import Path

from scenedetect import ContentDetector, open_video
from scenedetect.scene_manager import SceneManager


def detect_scenes(video_path: Path) -> list[dict]:
    video = open_video(str(video_path))
    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=27.0, min_scene_len=12))
    manager.detect_scenes(video=video, show_progress=False)
    scene_list = manager.get_scene_list()
    if not scene_list:
        duration = float(video.duration.get_seconds())
        return [{"index": 0, "start": 0.0, "end": duration, "duration": duration}]
    return [{
        "index": index,
        "start": float(start.get_seconds()),
        "end": float(end.get_seconds()),
        "duration": float(end.get_seconds() - start.get_seconds()),
    } for index, (start, end) in enumerate(scene_list)]
