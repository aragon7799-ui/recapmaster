# RecapMaster AI — Delivery TODO

Status markers: `[ ]` unresolved, `[~]` implemented in part, `[x]` complete with evidence.

## 1. Working scaffold and serving

- [ ] The repository contains a mobile-responsive Next.js frontend, a Python FastAPI backend, pinned `package.json`/lockfile and `requirements.txt`, `.env.example`, Dockerfile, Burmese README, `/uploads` and `/outputs` workspaces, project structure documentation, and `public/manus-routes.json`.
- [ ] FastAPI exposes an unauthenticated health endpoint and the frontend is served on the configured Preview port; the development proxy and production single-listener serving path use relative browser URLs and honor `PORT`.
- [ ] TypeScript and Python diagnostics are registered and actionable diagnostics are resolved before delivery.

## 2. Real input ingestion and validation

- [ ] A user can paste a YouTube/video URL or upload a video file from a phone gallery/camera through a real upload handler.
- [ ] YouTube URLs use real `yt-dlp`; direct MP4/video URLs use real fetch; blocked or invalid sources show the real error and suggest direct upload.
- [ ] Uploaded and fetched media receives real duration, format, size, and codec validation before a job is accepted; no fake media or hardcoded sample input is used.
- [ ] Input files are tracked in the application index and disposable processing paths are separated from durable artifact records.

## 3. Real analysis pipeline

- [ ] Audio is extracted and transcribed with real faster-whisper when configured, with the documented real Whisper-compatible service adapter available for managed runtime execution; transcript text and timed segments are persisted.
- [ ] PySceneDetect performs real scene-cut detection and timestamps are persisted.
- [ ] A real LLM call analyzes key characters, plot points, climax, ending, and selected scenes, with honest missing-key/provider errors.
- [ ] A real LLM call produces Unicode Burmese output, paraphrased rather than copied dialogue, structured as hook, intro, plot, key scenes, climax, ending, and personal commentary/opinion, with length matched to Short 60–90s, Standard 5–8min, or Full 10–15min.

## 4. Real narration, subtitles, and media composition

- [ ] Edge-TTS produces a real Burmese MP3/WAV using `my-MM-ThihaNeural` or `my-MM-NilarNeural`, verifies audio duration against the target, and logs a real fallback/error when a voice fails.
- [ ] Selected source clips are cut at real timestamps with FFmpeg; clip lengths are limited and the final composition contains the actual source footage.
- [ ] Music-heavy source audio is detected, muted/replaced where configured, and every copyright-safe action is logged; commentary voice and disclaimer footer are actually rendered.
- [ ] Generated SRT subtitles are burned into the video using FFmpeg; vertical output repositions captions into safe zones.
- [ ] An uploaded logo is actually overlaid and repositioned into a safe corner per aspect ratio.
- [ ] The master is concatenated and encoded as a real MP4 with H.264 High or the selected HEVC option, CRF/bitrate quality rules, `yuv420p`, preserved source FPS, AAC stereo, and `loudnorm` targeting -14 LUFS.

## 5. Multi-platform rendering

- [ ] The user can select multiple platforms at once: YouTube Standard, YouTube Shorts, TikTok, Facebook Reels, Facebook Feed, Instagram Reels, Instagram Feed, Instagram Story, X/Twitter, Threads, Telegram, and Generic 4:5.
- [ ] Each selected platform receives an independent real FFmpeg re-render with its required aspect ratio, crop/pad/reframe behavior, safe-area subtitle placement, safe-area logo placement, and selected quality resolution.
- [ ] Renders run as one tracked job, in parallel where possible, with per-platform real progress and partial-failure preservation.
- [ ] Files use deterministic per-platform names such as `recap_YYYY-MM-DD_youtube_1080p.mp4`; verified outputs each have a real download button and a ZIP download.

## 6. Quality controls and verification

- [ ] The UI exposes Draft/480p, Standard/720p, High/1080p default, Ultra/1440p/2K, and Cinema/4K quality levels, with real estimates based on source duration/bitrate and actual post-render sizes.
- [ ] Upscaling uses Lanczos only when the chosen quality exceeds source; motion interpolation is not used.
- [ ] Every completed output is inspected with real FFprobe and the UI exposes codec, resolution, bitrate, duration, FPS, audio codec, and file size.
- [ ] A result cannot be marked successful or offered as verified until the file exists and FFprobe succeeds.

## 7. UI, history, and metadata

- [ ] The UI is Burmese-first with dark mode, responsive mobile upload controls, multi-select platform chips with icons, quality selection, tone/spoiler/language/length controls, real stage progress, real per-platform progress, real preview players, real download buttons, and real error/log display.
- [ ] Project history lists real prior jobs and their terminal states, artifacts, logs, and verification data; no seeded fake history is used.
- [ ] The system produces real Burmese YouTube title/description/tags appropriate to the selected output and a real thumbnail suggestion tied to the analyzed source.

## 8. Durable storage, errors, and operations

- [ ] Database records use deterministic additive migrations and retain project/job/artifact/event state across process restarts; media uses durable project storage when configured and never relies on a published container filesystem for persistence.
- [ ] Structured logs record every pipeline stage and every external tool/API call that can be safely logged.
- [ ] Missing API key, FFmpeg failure with stderr, TTS voice failure/fallback, platform render failure, unsupported input, storage failure, and timeout states are shown honestly and do not create false success.
- [ ] Long-running work is a background job with SSE/status lookup, not a single blocking request; retry behavior is limited to retryable transient failures and never repeats an unchanged permanent request indefinitely.

## 9. Real evidence and delivery

- [ ] A real short test video is processed end-to-end without fake data, including real download/upload, transcription, scene detection, LLM analysis/script, Burmese TTS, FFmpeg composition, and at least two platform renders.
- [ ] The final response or README includes the actual FFprobe output for each tested output, proving codec, resolution, bitrate, duration, and file size, plus real terminal logs for FFmpeg, Whisper/transcription, TTS, and LLM calls.
- [ ] The project checkpoint contains only tested source/configuration and no secrets, sample fake outputs, or misleading claims.
