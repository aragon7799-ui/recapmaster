from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import httpx

from ..config import settings
from .media import run_command


def extract_audio(video_path: Path, workdir: Path) -> Path:
    # Compressed mono audio keeps long films below hosted transcription request
    # limits while remaining compatible with Whisper and faster-whisper.
    workdir.mkdir(parents=True, exist_ok=True)
    audio_path = workdir / "source.mp3"
    run_command([settings.ffmpeg_bin, "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k", str(audio_path)], timeout=900)
    return audio_path


def _service_transcribe(audio_path: Path) -> dict[str, Any]:
    if not settings.manus_api_url or not settings.manus_api_key:
        raise RuntimeError("No managed transcription credentials are available.")
    with audio_path.open("rb") as handle:
        response = httpx.post(
            f"{settings.manus_api_url}/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.manus_api_key}"},
            files={"file": (audio_path.name, handle, mimetypes.guess_type(audio_path.name)[0] or "audio/mpeg")},
            data={"model": "whisper-1", "prompt": "The working language may include Burmese Myanmar Unicode and film terminology."},
            timeout=1800,
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    return {"provider": "managed-whisper", "language": payload.get("language"), "text": payload.get("text", ""), "segments": payload.get("segments", [])}


def _faster_whisper(audio_path: Path) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    model = WhisperModel(settings.whisper_model, device=settings.whisper_device, compute_type=settings.whisper_compute_type)
    segments, info = model.transcribe(str(audio_path), beam_size=5, vad_filter=True)
    items = []
    texts = []
    for index, segment in enumerate(segments):
        text = segment.text.strip()
        if text:
            texts.append(text)
            items.append({"id": index, "start": float(segment.start), "end": float(segment.end), "text": text})
    return {"provider": "faster-whisper", "language": info.language, "text": " ".join(texts), "segments": items}


def transcribe(video_path: Path, workdir: Path) -> dict[str, Any]:
    audio_path = extract_audio(video_path, workdir)
    provider = settings.transcription_provider.lower()
    if provider in {"service", "managed"}:
        return _service_transcribe(audio_path)
    try:
        return _faster_whisper(audio_path)
    except Exception as faster_error:
        if settings.manus_api_url and settings.manus_api_key:
            result = _service_transcribe(audio_path)
            result["fallback_reason"] = str(faster_error)
            return result
        raise RuntimeError(f"faster-whisper failed and no managed fallback is configured: {faster_error}") from faster_error
