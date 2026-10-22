from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PLATFORMS = {
    "youtube": {"label": "YouTube", "ratio": "16:9", "width": 1920, "height": 1080},
    "youtube_shorts": {"label": "YouTube Shorts", "ratio": "9:16", "width": 1080, "height": 1920},
    "tiktok": {"label": "TikTok", "ratio": "9:16", "width": 1080, "height": 1920},
    "facebook_reels": {"label": "Facebook Reels", "ratio": "9:16", "width": 1080, "height": 1920},
    "facebook_feed": {"label": "Facebook Feed", "ratio": "1:1", "width": 1080, "height": 1080},
    "instagram_reels": {"label": "Instagram Reels", "ratio": "9:16", "width": 1080, "height": 1920},
    "instagram_feed": {"label": "Instagram Feed", "ratio": "1:1", "width": 1080, "height": 1080},
    "instagram_story": {"label": "Instagram Story", "ratio": "9:16", "width": 1080, "height": 1920},
    "x": {"label": "X (Twitter)", "ratio": "16:9", "width": 1280, "height": 720},
    "threads": {"label": "Threads", "ratio": "9:16", "width": 1080, "height": 1920},
    "telegram": {"label": "Telegram", "ratio": "16:9", "width": 1280, "height": 720},
    "generic_4_5": {"label": "Generic 4:5", "ratio": "4:5", "width": 1080, "height": 1350},
}

QUALITY = {
    "draft": {"label": "Draft", "height": 480, "crf": 26, "bitrate": "2M"},
    "standard": {"label": "Standard", "height": 720, "crf": 22, "bitrate": "5M"},
    "high": {"label": "High", "height": 1080, "crf": 20, "bitrate": "8M"},
    "ultra": {"label": "Ultra", "height": 1440, "crf": 19, "bitrate": "14M"},
    "cinema": {"label": "Cinema", "height": 2160, "crf": 18, "bitrate": "20M"},
}

LENGTH_SECONDS = {"short": (60, 90), "standard": (300, 480), "full": (600, 900)}


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    upload_dir: Path
    output_dir: Path
    database_url: str
    max_upload_bytes: int
    max_source_duration_seconds: int
    manus_api_url: str
    manus_api_key: str
    openai_api_base: str
    openai_api_key: str
    llm_model: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    transcription_provider: str
    ffmpeg_bin: str
    ffprobe_bin: str
    ytdlp_bin: str
    royalty_free_music_path: str

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parents[2]
        data_dir = Path(os.getenv("APP_DATA_DIR", str(root / ".data"))).resolve()
        upload_dir = Path(os.getenv("UPLOAD_DIR", str(root / "uploads"))).resolve()
        output_dir = Path(os.getenv("OUTPUT_DIR", str(root / "outputs"))).resolve()
        for directory in (data_dir, upload_dir, output_dir):
            directory.mkdir(parents=True, exist_ok=True)
        database_url = os.getenv("DATABASE_URL", "").strip() or f"sqlite:///{data_dir / 'recapmaster.sqlite3'}"
        manus_api_url = os.getenv("MANUS_API_URL", "").rstrip("/")
        manus_api_key = os.getenv("MANUS_API_KEY", "")
        return cls(
            root=root,
            data_dir=data_dir,
            upload_dir=upload_dir,
            output_dir=output_dir,
            database_url=database_url,
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024))),
            max_source_duration_seconds=int(os.getenv("MAX_SOURCE_DURATION_SECONDS", "14400")),
            manus_api_url=manus_api_url,
            manus_api_key=manus_api_key,
            openai_api_base=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            whisper_model=os.getenv("FASTER_WHISPER_MODEL", "small"),
            whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
            whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            transcription_provider=os.getenv("TRANSCRIPTION_PROVIDER", "service" if manus_api_url and manus_api_key else "auto"),
            ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg"),
            ffprobe_bin=os.getenv("FFPROBE_BIN", "ffprobe"),
            ytdlp_bin=os.getenv("YTDLP_BIN", "yt-dlp"),
            royalty_free_music_path=os.getenv("ROYALTY_FREE_MUSIC_PATH", ""),
        )


settings = Settings.from_env()
