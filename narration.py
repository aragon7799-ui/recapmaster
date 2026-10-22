from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from .media import ffprobe_json, media_summary


VOICES = ["my-MM-ThihaNeural", "my-MM-NilarNeural"]


async def _synthesize(text: str, path: Path, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice=voice, rate="+0%", volume="+0%")
    await communicate.save(str(path))


def synthesize_burmese(text: str, path: Path) -> dict:
    errors: list[str] = []
    for voice in VOICES:
        try:
            asyncio.run(_synthesize(text, path, voice))
            meta = media_summary(ffprobe_json(path))
            if meta["duration"] <= 0:
                raise RuntimeError("TTS output has zero duration")
            return {"voice": voice, "duration": meta["duration"], "size_bytes": meta["size_bytes"], "fallback_errors": errors}
        except Exception as exc:
            errors.append(f"{voice}: {exc}")
    raise RuntimeError("All Burmese Edge-TTS voices failed: " + " | ".join(errors))
