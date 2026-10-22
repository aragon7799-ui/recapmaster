from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import PLATFORMS, QUALITY
from .media import escape_filter_path, ffprobe_json, media_summary, run_command, write_srt


def resolution_for(platform: str, quality: str) -> tuple[int, int]:
    preset = PLATFORMS[platform]
    height = {"draft": 480, "standard": 720, "high": 1080, "ultra": 1440, "cinema": 2160}[quality]
    ratio = preset["width"] / preset["height"]
    if platform in {"x", "telegram"} and quality in {"draft", "standard", "high"}:
        return (preset["width"], preset["height"] if quality != "high" else preset["height"])
    if ratio < 1:
        width = height
        return width, int(round(width / ratio / 2) * 2)
    width = int(round(height * ratio / 2) * 2)
    return width, height


def _select_scenes(scenes: list[dict], duration: float) -> list[dict]:
    ordered = sorted(scenes, key=lambda item: item["start"])
    if not ordered:
        return []
    selected: list[dict] = []
    total = 0.0
    stride = max(1, len(ordered) // 18)
    candidates = ordered[::stride]
    if ordered[-1] not in candidates:
        candidates.append(ordered[-1])
    for scene in candidates:
        if total >= duration:
            break
        available = min(float(scene["duration"]), duration - total)
        if available < 0.5:
            continue
        selected.append({"start": float(scene["start"]), "end": float(scene["start"]) + available, "duration": available})
        total += available
    if not selected:
        scene = ordered[0]
        selected.append({"start": float(scene["start"]), "end": min(float(scene["end"]), float(scene["start"]) + duration), "duration": duration})
    return selected


def cut_clips(source: Path, scenes: list[dict], workdir: Path) -> list[Path]:
    workdir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for index, scene in enumerate(scenes):
        clip = workdir / f"clip_{index:03d}.mp4"
        run_command([
            "ffmpeg", "-y", "-ss", f"{scene['start']:.3f}", "-to", f"{scene['end']:.3f}", "-i", str(source),
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(clip),
        ], timeout=900)
        clips.append(clip)
    if not clips:
        raise RuntimeError("No real source clips were selected.")
    return clips


def create_music_bed(duration: float, workdir: Path, configured_path: str = "") -> Path:
    if configured_path:
        candidate = Path(configured_path).expanduser().resolve()
        if not candidate.exists():
            raise RuntimeError(f"Configured royalty-free music file does not exist: {candidate}")
        return candidate
    bed = workdir / "generated_royalty_free_bed.wav"
    run_command([
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=196:sample_rate=48000:duration={duration:.3f}",
        "-f", "lavfi", "-i", f"sine=frequency=293.66:sample_rate=48000:duration={duration:.3f}",
        "-filter_complex", "[0:a][1:a]amix=inputs=2,volume=0.06", "-c:a", "pcm_s16le", str(bed),
    ], timeout=300)
    return bed


def script_segments(script: str, duration: float) -> list[dict]:
    sentences = [item.strip() for item in script.replace("။", "။\n").splitlines() if item.strip()]
    if not sentences:
        sentences = [script.strip()]
    step = max(0.8, duration / len(sentences))
    return [{"start": index * step, "end": min(duration, (index + 1) * step), "text": sentence} for index, sentence in enumerate(sentences)]


def _concat_file(clips: list[Path], path: Path) -> None:
    path.write_text("\n".join(f"file '{str(clip).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'" for clip in clips) + "\n", encoding="utf-8")


def compose_master(clips: list[Path], narration: Path, music: Path, script: str, duration: float, quality: str, logo: Path | None, workdir: Path) -> tuple[Path, dict]:
    concat_path = workdir / "clips.txt"
    srt_path = workdir / "captions.srt"
    master = workdir / "master.mp4"
    _concat_file(clips, concat_path)
    write_srt(srt_path, script_segments(script, duration))
    q = QUALITY[quality]
    subtitle = escape_filter_path(srt_path)
    video_chain = f"[0:v]subtitles='{subtitle}':force_style='FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=1,MarginV=100,Alignment=2'[sub]"
    maps = "[sub]"
    inputs = ["-f", "concat", "-safe", "0", "-i", str(concat_path), "-i", str(narration), "-i", str(music)]
    if logo:
        inputs += ["-loop", "1", "-i", str(logo)]
        video_chain += ";[3:v]scale=180:-1[logo];[sub][logo]overlay=x=48:y=48:format=auto[v]"
        maps = "[v]"
    audio_chain = ";[1:a]aresample=48000,volume=1.0[narr];[2:a]aresample=48000,volume=0.16[music];[narr][music]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    command = ["ffmpeg", "-y", *inputs, "-filter_complex", video_chain + audio_chain, "-map", maps, "-map", "[a]", "-t", f"{duration:.3f}", "-c:v", "libx264", "-profile:v", "high", "-crf", str(q["crf"]), "-maxrate", q["bitrate"], "-bufsize", str(int(q["bitrate"].rstrip('M')) * 2) + "M", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", str(master)]
    run_command(command, timeout=1800)
    return master, media_summary(ffprobe_json(master))


def render_platform(master: Path, platform: str, quality: str, output_dir: Path, logo: Path | None) -> tuple[Path, dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = resolution_for(platform, quality)
    preset = PLATFORMS[platform]
    q = QUALITY[quality]
    output = output_dir / f"recap_{platform}_{quality}.mp4"
    crop = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
    video_chain = f"[0:v]{crop}[scaled]"
    maps = "[scaled]"
    inputs = ["-i", str(master)]
    if logo:
        inputs += ["-loop", "1", "-i", str(logo)]
        video_chain += ";[1:v]scale=-1:min(180\\,ih*0.12)[logo];[scaled][logo]overlay=x=48:y=48:format=auto[v]"
        maps = "[v]"
    run_command([
        "ffmpeg", "-y", *inputs, "-filter_complex", video_chain, "-map", maps, "-map", "0:a?", "-c:v", "libx264", "-profile:v", "high", "-crf", str(q["crf"]), "-maxrate", q["bitrate"], "-bufsize", str(int(q["bitrate"].rstrip('M')) * 2) + "M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", str(output),
    ], timeout=1800)
    return output, media_summary(ffprobe_json(output))
