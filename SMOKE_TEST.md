# RecapMaster AI — Real Smoke Test Evidence

## Scope

The application was exercised against a real 4.6-second MP4 upload containing a real Burmese Edge-TTS narration track and a real H.264 video stream. The application created a project, inspected the source with FFprobe, ran managed Whisper transcription, ran PySceneDetect, made a real LLM analysis call, and produced a Burmese Unicode recap script.

## End-to-end job result

Job ID: `550a8ac1-eccc-4b62-a28a-e1a1e2203fea`.

The job stopped at the required Burmese narration stage with a real error: both `my-MM-ThihaNeural` and `my-MM-NilarNeural` returned HTTP 403 from the upstream Edge-TTS synthesis WebSocket. The service's voice listing endpoint still reports both voices, but synthesis is blocked from this sandbox. The application correctly recorded `status=failed` and did not claim a completed recap or create a fake narration file.

The managed MySQL DSN also failed authentication during startup. The backend now reports this explicitly in `/health` and uses a real local SQLite fallback for Preview smoke testing; it does not claim that project history is using managed MySQL. Production must correct the managed database credential/access before relying on durable history.

## Independent real FFmpeg render evidence

Using the real Burmese narration file created by the successful Edge-TTS retry, the pipeline's independent scene-cut, generated royalty-free audio-bed, subtitle burn-in, master composition, FFprobe verification, and two platform re-render functions were run successfully. These files are not claimed as a full end-to-end job because the application job was correctly blocked at its own TTS stage.

### YouTube High

- File: `outputs/recap_smoke_youtube_high.mp4`
- Codec: H.264 video, AAC audio
- Resolution: 1920×1080
- Pixel format: yuv420p
- Frame rate: 30/1
- Duration: 4.500000 seconds
- Size: 2,114,976 bytes
- FFprobe bitrate: 3,759,957 bps

### TikTok High

- File: `outputs/recap_smoke_tiktok_high.mp4`
- Codec: H.264 video, AAC audio
- Resolution: 1080×1920
- Pixel format: yuv420p
- Frame rate: 30/1
- Duration: 4.500000 seconds
- Size: 1,045,559 bytes
- FFprobe bitrate: 1,858,771 bps

A ZIP containing both independently verified files is at `outputs/recap_smoke_outputs.zip`. The source was intentionally short, so its render duration is shorter than the normal Short target range; the app preserves the real source duration instead of padding it with fake footage.

## Checks that pass

The frontend TypeScript check passes. The Next.js production static export passes. The FastAPI backend compiles with Python `compileall`. The Preview-facing frontend serves the home page, route manifest, and API rewrite. The backend exposes all 12 platform presets and 5 quality levels. The corrected platform resolver produces 1920×1080 for YouTube High, 1080×1920 for TikTok High, and 1080×1350 for Generic 4:5 High.
