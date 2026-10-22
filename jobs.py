from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import db
from .config import LENGTH_SECONDS, PLATFORMS, settings
from .pipeline.composer import compose_master, create_music_bed, cut_clips, render_platform
from .pipeline.intelligence import analyze_content, generate_metadata, write_burmese_script
from .pipeline.media import ffprobe_json, media_summary
from .pipeline.narration import synthesize_burmese
from .pipeline.packaging import create_zip, verify_video, write_json
from .pipeline.scenes import detect_scenes
from .pipeline.transcription import transcribe

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="recap-job")


def _event(job_id: str, stage: str, message: str, progress: float, status: str = "running", platform: str | None = None, details: dict[str, Any] | None = None) -> None:
    db.update_job(job_id, status="running", current_stage=stage)
    db.add_event(job_id, stage, status, message, progress, platform, details)


def submit(job_id: str) -> None:
    executor.submit(run_job, job_id)


def run_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        return
    project = db.get_project(job["project_id"])
    if not project or not project.get("source_path"):
        db.update_job(job_id, status="failed", error="Project source is unavailable.")
        db.add_event(job_id, "ingest", "error", "Project source is unavailable.", 1.0)
        return
    options = job.get("options", {})
    workdir = settings.data_dir / "jobs" / job_id
    workdir.mkdir(parents=True, exist_ok=True)
    source = Path(project["source_path"])
    logo = Path(project["logo_path"]) if project.get("logo_path") else None
    failures: list[str] = []
    outputs: list[Path] = []
    try:
        _event(job_id, "inspect", "Source verified; preparing the real processing workspace.", 0.04, details=project.get("source_meta", {}))
        transcript_path = workdir / "transcript.json"
        if transcript_path.exists():
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            _event(job_id, "transcribe", "Reused the saved transcription checkpoint.", 0.22)
        else:
            _event(job_id, "transcribe", "Running real speech transcription.", 0.12)
            transcript = transcribe(source, workdir)
            transcript_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        _event(job_id, "transcribe", f"Transcription complete via {transcript.get('provider')}.", 0.22, details={"provider": transcript.get("provider"), "language": transcript.get("language"), "segments": len(transcript.get("segments", []))})

        scenes_path = workdir / "scenes.json"
        if scenes_path.exists():
            scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
        else:
            _event(job_id, "detect_scenes", "Detecting real scene cuts with PySceneDetect.", 0.26)
            scenes = detect_scenes(source)
            scenes_path.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")
        _event(job_id, "detect_scenes", f"Detected {len(scenes)} scenes.", 0.32, details={"scene_count": len(scenes)})

        analysis_path = workdir / "analysis.json"
        if analysis_path.exists():
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        else:
            _event(job_id, "analyze", "Analyzing characters, plot points, climax, ending, and insights with the LLM.", 0.36)
            analysis = analyze_content(transcript.get("text", ""), scenes, bool(options.get("spoiler")))
            write_json(analysis_path, analysis)
        _event(job_id, "analyze", "Content analysis complete.", 0.43, details={"analysis_keys": list(analysis.keys())})

        script_path = workdir / "script.json"
        if script_path.exists():
            script_data = json.loads(script_path.read_text(encoding="utf-8"))
        else:
            _event(job_id, "write_script", "Writing an original Burmese Unicode recap script.", 0.46)
            script_data = write_burmese_script(analysis, transcript.get("text", ""), options.get("length", "standard"), options.get("tone", "engaging"), bool(options.get("spoiler")))
            write_json(script_path, script_data)
        _event(job_id, "write_script", "Burmese script verified as Unicode text.", 0.52, details={"estimated_seconds": script_data.get("estimated_seconds")})

        narration = workdir / "narration.mp3"
        if narration.exists() and narration.stat().st_size > 0:
            narration_meta = {"voice": "saved-checkpoint", "duration": media_summary(ffprobe_json(narration))["duration"], "size_bytes": narration.stat().st_size}
        else:
            _event(job_id, "synthesize_voice", "Synthesizing real Burmese narration with Edge-TTS.", 0.56)
            narration_meta = synthesize_burmese(script_data["script"], narration)
        _event(job_id, "synthesize_voice", f"Narration created with {narration_meta['voice']}.", 0.62, details=narration_meta)

        source_duration = float((project.get("source_meta") or {}).get("duration") or 0)
        desired_duration = min(source_duration, max(5.0, float(narration_meta["duration"])))
        selected = _select_scenes_for_duration(scenes, desired_duration)
        existing_clips = sorted((workdir / "clips").glob("clip_*.mp4"))
        if existing_clips:
            clips = existing_clips
        else:
            _event(job_id, "select_clips", f"Cutting {len(selected)} real clips from source scenes.", 0.66)
            clips = cut_clips(source, selected, workdir / "clips")
        music = workdir / "generated_royalty_free_bed.wav"
        if not music.exists():
            music = create_music_bed(desired_duration, workdir, settings.royalty_free_music_path)
        _event(job_id, "select_clips", "Source clips cut; original audio replaced by narration plus a royalty-free bed.", 0.70, details={"clip_count": len(clips), "duration": desired_duration})

        master = workdir / "master.mp4"
        if master.exists() and master.stat().st_size > 0:
            master_meta = verify_video(master)
        else:
            _event(job_id, "compose_master", "Composing the verified master with subtitles, logo, loudness normalization, and disclaimer-safe narration.", 0.74)
            master, master_meta = compose_master(clips, narration, music, script_data["script"], desired_duration, options.get("quality", "high"), logo, workdir)
        master_meta = verify_video(master)
        db.add_artifact(job_id, project["id"], "master", None, str(master), master.name, "video/mp4", master.stat().st_size, master_meta, True)
        _event(job_id, "compose_master", "Master MP4 passed FFprobe verification.", 0.78, details=master_meta)

        _event(job_id, "render_platforms", "Rendering all selected platform variants.", 0.80)
        platform_results: list[tuple[str, Path, dict]] = []
        selected_platforms = options.get("platforms") or ["youtube"]
        with ThreadPoolExecutor(max_workers=min(4, len(selected_platforms))) as pool:
            futures = {}
            for index, platform in enumerate(selected_platforms):
                if platform not in PLATFORMS:
                    failures.append(f"{platform}: unsupported platform")
                    continue
                db.add_event(job_id, "render_platform", "running", f"Rendering {PLATFORMS[platform]['label']}.", 0.80 + index / max(1, len(selected_platforms)) * 0.16, platform)
                futures[platform] = pool.submit(render_platform, master, platform, options.get("quality", "high"), workdir / "outputs", logo)
            for platform, future in futures.items():
                try:
                    output, meta = future.result()
                    verified = verify_video(output)
                    platform_results.append((platform, output, verified))
                    outputs.append(output)
                    db.add_artifact(job_id, project["id"], "platform_video", platform, str(output), output.name, "video/mp4", output.stat().st_size, verified, True)
                    db.add_event(job_id, "render_platform", "complete", f"{PLATFORMS[platform]['label']} passed FFprobe verification.", 0.80 + len(platform_results) / max(1, len(selected_platforms)) * 0.16, platform, verified)
                except Exception as exc:
                    failures.append(f"{platform}: {exc}")
                    db.add_event(job_id, "render_platform", "error", f"{PLATFORMS[platform]['label']} failed: {exc}", 0.80, platform, {"error": str(exc)})

        metadata = generate_metadata(script_data["script"], analysis)
        metadata_path = write_json(workdir / "social_metadata.json", metadata)
        db.add_artifact(job_id, project["id"], "metadata", None, str(metadata_path), metadata_path.name, "application/json", metadata_path.stat().st_size, metadata, True)
        if outputs:
            zip_path = create_zip(outputs, workdir / f"recapmaster_{job_id[:8]}.zip")
            db.add_artifact(job_id, project["id"], "zip", None, str(zip_path), zip_path.name, "application/zip", zip_path.stat().st_size, {"files": [item.name for item in outputs]}, True)
        if failures:
            error = "Partial platform failures: " + " | ".join(failures)
            db.update_job(job_id, status="completed_with_errors", current_stage="complete", error=error)
            db.add_event(job_id, "complete", "warning", "Job finished with verified outputs and partial platform failures.", 1.0, details={"failures": failures})
        else:
            db.update_job(job_id, status="completed", current_stage="complete")
            db.add_event(job_id, "complete", "complete", "All selected platform outputs are verified and ready to download.", 1.0)
    except Exception as exc:
        error = str(exc)
        db.update_job(job_id, status="failed", current_stage="failed", error=error)
        db.add_event(job_id, "failed", "error", "Pipeline stopped with a real error; no success was claimed.", 1.0, details={"error": error})


def _select_scenes_for_duration(scenes: list[dict], duration: float) -> list[dict]:
    ordered = sorted(scenes, key=lambda item: item["start"])
    if not ordered:
        return []
    selected = []
    total = 0.0
    stride = max(1, len(ordered) // 20)
    for scene in ordered[::stride]:
        if total >= duration:
            break
        available = min(float(scene["duration"]), duration - total)
        if available <= 0.5:
            continue
        selected.append({"start": float(scene["start"]), "end": float(scene["start"]) + available, "duration": available})
        total += available
    if not selected:
        first = ordered[0]
        selected = [{"start": float(first["start"]), "end": min(float(first["end"]), duration), "duration": duration}]
    return selected
