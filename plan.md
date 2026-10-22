# RecapMaster AI — Implementation Plan

## Scope and implementation approach

RecapMaster AI will be implemented as a managed Web project with a mobile-first Next.js frontend and a Python FastAPI media-processing backend. The backend owns all trusted work: URL/file ingestion, validation, job orchestration, transcription, scene detection, LLM analysis and Burmese script generation, TTS, FFmpeg composition, platform renders, FFprobe inspection, structured logging, ZIP creation, and durable job/project records. The browser receives only browser-safe configuration and polls or subscribes to server-sent progress events; provider credentials never enter client code.

The first implementation will use the Manus-provided OpenAI-compatible LLM and Whisper-compatible transcription surfaces when their runtime credentials are available, while preserving provider adapters for an independently configured OpenAI-compatible endpoint. The media pipeline will use the requested real command-line tools and libraries: FFmpeg/FFprobe, yt-dlp, PySceneDetect, faster-whisper when the local model path is configured, edge-tts, MoviePy utilities where useful, and Python ZIP/file handling. A job is terminally failed when a required real stage fails; the UI will never manufacture completion, progress, transcript, audio, or video data.

Because generated media and uploaded movies are large and the published filesystem is ephemeral, durable application indexes live in the managed MySQL database and media is stored under project storage when a storage credential is available. The local `/uploads` and `/outputs` folders remain the active processing workspace and are treated as disposable caches. Every persisted artifact records its stable storage address, local processing path when present, size, MIME type, checksum, and lifecycle state.

The end-to-end job is staged so each stage produces a concrete artifact and structured event: `ingest → inspect → transcribe → detect_scenes → analyze → write_script → synthesize_voice → select_clips → compose_master → render_platforms → verify → package`. Platform renders are independently tracked, so a failed platform does not erase successful outputs. ZIP packaging is created only from verified output files.

## Project structure

```text
recapmaster/
├── frontend/                         # Next.js mobile-responsive Burmese control room
│   ├── app/page.tsx                  # upload/configuration/workbench UI
│   ├── app/globals.css               # dark editorial visual system
│   ├── components/                   # platform chips, timeline, progress, result cards
│   ├── lib/api.ts                    # typed relative API client and SSE helpers
│   └── next.config.ts                # development proxy to FastAPI
├── backend/
│   ├── app/main.py                   # FastAPI routes, health, static production serving
│   ├── app/config.py                 # environment and feature configuration
│   ├── app/db.py                     # MySQL connection and schema initialization
│   ├── app/models.py                 # job/project/artifact records
│   ├── app/schemas.py                # request/response validation
│   ├── app/jobs.py                   # background job lifecycle and event publication
│   ├── app/pipeline/                 # one module per real processing stage
│   │   ├── ingest.py                 # upload/URL fetch, yt-dlp, validation
│   │   ├── media.py                  # ffprobe, ffmpeg, clip and render helpers
│   │   ├── transcription.py          # faster-whisper and platform STT adapter
│   │   ├── scenes.py                 # PySceneDetect cut detection
│   │   ├── intelligence.py           # LLM analysis and Burmese script generation
│   │   ├── narration.py               # edge-tts Burmese voices and duration checks
│   │   ├── subtitles.py               # SRT generation and safe-zone layout
│   │   └── packaging.py               # verification and ZIP output
│   └── tests/                         # deterministic unit/API tests
├── public/manus-routes.json           # complete page route manifest
├── scripts/                           # migrations, smoke checks, demo runner
├── uploads/.gitkeep                   # disposable local input workspace
├── outputs/.gitkeep                   # disposable local output workspace
├── .env.example                       # every user/provider setting, no values
├── Dockerfile                         # production FastAPI + built frontend image
├── package.json / pnpm-lock.yaml      # pinned frontend toolchain
├── pnpm-workspace.yaml                # reviewed lifecycle build policy
├── requirements.txt                   # pinned Python dependencies
├── README.md                          # Burmese setup and operation guide
├── app.config.ts                      # project logo metadata
├── plan.md
└── TODO.md
```

## Backend and frontend serving

During development, FastAPI listens on port 8000 and Next.js listens on port 3000. Next rewrites `/api/*` to the FastAPI endpoint, so the Preview-facing browser uses relative URLs only. The runtime configuration will declare the backend endpoint and keep the primary Preview port at 3000. In production, the Docker image builds the Next static export and FastAPI serves it plus `/api/*` from a single listener honoring `PORT` (default 3000); `/health` is unauthenticated and suitable for readiness.

The API surface will include:

- `POST /api/projects` to create a project and accept one URL or upload.
- `POST /api/jobs` to validate options and enqueue a real pipeline job.
- `GET /api/jobs/{id}` for current state, artifacts, FFprobe data, errors, and logs.
- `GET /api/jobs/{id}/events` for SSE progress events with stage and platform updates.
- `GET /api/artifacts/{id}/download` for verified outputs and ZIPs.
- `GET /api/history` for durable project history.
- `GET /health` for readiness.

## Data and error boundaries

Database writes are additive and idempotent. A job stores the requested options, pipeline version, stage state, event log, errors, artifact metadata, and platform results. Media writes use random non-colliding keys. Provider errors are preserved in structured logs with command, exit code, and stderr where safe. Missing API credentials, missing binaries, unsupported formats, blocked YouTube downloads, TTS failures, and partial platform failures are shown as actionable errors rather than hidden.

The UI is Burmese-first but keeps technical diagnostics, codec names, command names, and file paths legible. It includes accessible labels, keyboard support, drag/drop plus mobile file selection, real client-side validation, real server progress, dark mode, and an explicit “not complete until verified” status. No sample video, sample transcript, fake estimate, simulated progress, or hardcoded successful artifact is included.

## Design direction

### Alternatives considered

1. **Editorial control room** (0.07): a dark, cinematic post-production workspace with a bright signal color and timeline-oriented composition.
2. **Quiet Burmese studio** (0.05): warm paper-like panels, restrained typography, and a calm writing-first workflow.
3. **Neon creator console** (0.03): high-contrast streaming-era controls with vivid status colors and strong motion.

### Chosen movement: editorial control room

**Design Movement:** Contemporary broadcast post-production software with the atmosphere of a film-editing suite, translated into a Burmese creator workflow.

**Core Principles:** Evidence over decoration; progressive disclosure from source to render; dense but readable operational context; every success state tied to a real artifact.

**Color Philosophy:** Near-black graphite establishes the screening room; warm off-white text keeps Burmese copy comfortable; a signature saffron-gold `#F2B84B` signals creative intelligence and verified readiness; cyan and red are reserved for live system states, not branding.

**Layout Paradigm:** A left source rail, a wide central workbench, and a right verification rail replace a centered card grid. The workbench changes from intake to pipeline to results without losing project context.

**Signature Elements:** A “film strip” progress spine for the pipeline; saffron-gold chapter markers; verification cards that expose real duration, resolution, bitrate, codec, and file size instead of ornamental metrics.

**Interaction Philosophy:** Controls remain close to the artifact they affect. Expensive actions are explicit, disabled when validation is incomplete, and accompanied by honest state text. Upload and render actions never pretend to be instant.

**Animation:** Use short 160–220ms transitions for panel changes, a restrained moving scanline only while a real job is running, and no looping celebratory animation on failure or unverified output. Respect reduced-motion preferences.

**Typography System:** Use `Noto Sans Myanmar` for Burmese UI text with `Inter` as the Latin/technical companion. Headings are compact and high contrast; metadata uses tabular numerals; technical logs use a monospace face.

**Brand Essence:** “Turn a film into a story your audience can finish” for Burmese creators who need a real, inspectable recap workflow; precise, cinematic, trustworthy.

**Brand Voice:** Headlines are direct and editorial; CTAs name the real action. Example lines: “ဇာတ်လမ်းကို အမှန်တကယ် ပြန်ပြောပါ” and “Render မပြီးမချင်း အောင်မြင်သည်ဟု မဆိုပါ”.

**Wordmark & Logo:** A compact `RM` mark built from two offset frame corners and a playhead notch, paired with a wordmark that uses the gold playhead as the cross-stroke of the `A` in AI.

**Signature Brand Color:** Saffron-gold `#F2B84B`.

## Implementation workflow

1. Establish the project files, route manifest, toolchain policies, FastAPI health endpoint, Next shell, and diagnostic checks.
2. Implement real input ingestion, file/URL validation, ffprobe inspection, and durable job records.
3. Implement stage adapters in isolation, starting with FFmpeg/FFprobe and scene detection, then transcription, LLM, TTS, subtitles, and composition.
4. Connect background jobs and SSE to the frontend, preserving partial failures and real logs.
5. Implement all platform presets, quality mapping, smart crop/pad, safe zones, logo placement, verification, and ZIP packaging.
6. Add project history, Burmese metadata generation, thumbnail suggestions, README, migrations, container build, and deployment configuration.
7. Run deterministic checks plus a real short-video smoke run. Only report outputs whose files exist and whose FFprobe values were read from those files.

The product remains open for the full requested scope until each corresponding TODO item has concrete evidence. Where a user-provided provider key, a model download, a royalty-free music asset, or device storage permission is genuinely required, the UI and README will state that dependency and fail honestly when it is absent.
