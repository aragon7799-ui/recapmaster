from __future__ import annotations

import asyncio
import json
import mimetypes
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import PLATFORMS, QUALITY, settings
from .jobs import submit
from .pipeline.ingest import download_source, validate_source
from .schemas import JobCreate

app = FastAPI(title="RecapMaster AI API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Stay comfortably below common hosted proxy request limits.
CHUNK_SIZE = 4 * 1024 * 1024
CHUNK_UPLOAD_DIR = settings.data_dir / "chunked-uploads"
CHUNK_LOCKS: dict[str, asyncio.Lock] = {}


@app.on_event("startup")
def startup() -> None:
    db.initialize()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "recapmaster-api", "version": app.version, "database": db.database_status}


@app.get("/api/platforms")
def platforms() -> dict:
    return {"platforms": PLATFORMS, "quality": QUALITY}


async def _save_upload(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with destination.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.max_upload_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded video exceeds the configured size limit.")
            handle.write(chunk)
    if total == 0:
        raise HTTPException(status_code=400, detail="Uploaded video is empty.")


@app.post("/api/uploads/init")
def init_chunk_upload(payload: dict) -> dict:
    filename = Path(str(payload.get("filename") or "source.mp4")).name
    size = int(payload.get("size") or 0)
    if size <= 0:
        raise HTTPException(status_code=400, detail="Upload size must be greater than zero.")
    if size > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Uploaded video exceeds the configured size limit.")
    upload_id = uuid.uuid4().hex
    session_dir = CHUNK_UPLOAD_DIR / upload_id
    session_dir.mkdir(parents=True, exist_ok=False)
    (session_dir / "session.json").write_text(json.dumps({"filename": filename, "size": size, "received_offsets": []}), encoding="utf-8")
    (session_dir / "source.part").touch()
    return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE}


@app.get("/api/uploads/{upload_id}")
def get_chunk_upload(upload_id: str) -> dict:
    session_file = CHUNK_UPLOAD_DIR / upload_id / "session.json"
    if not session_file.exists():
        raise HTTPException(status_code=404, detail="Upload session not found or expired.")
    session = json.loads(session_file.read_text(encoding="utf-8"))
    return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE, "size": session["size"], "received_offsets": session.get("received_offsets", [])}


@app.put("/api/uploads/{upload_id}/chunk")
async def upload_chunk(upload_id: str, request: Request, offset: int = 0) -> dict:
    session_dir = CHUNK_UPLOAD_DIR / upload_id
    session_file = session_dir / "session.json"
    if not session_file.exists():
        raise HTTPException(status_code=404, detail="Upload session not found or expired.")
    session = json.loads(session_file.read_text(encoding="utf-8"))
    chunk = await request.body()
    if not chunk:
        raise HTTPException(status_code=400, detail="Upload chunk is empty.")
    if len(chunk) > CHUNK_SIZE or offset < 0 or offset + len(chunk) > session["size"]:
        raise HTTPException(status_code=400, detail="Invalid upload chunk offset or size.")
    part = session_dir / "source.part"
    lock = CHUNK_LOCKS.setdefault(upload_id, asyncio.Lock())
    async with lock:
        with part.open("r+b") as handle:
            handle.seek(offset)
            handle.write(chunk)
        session = json.loads(session_file.read_text(encoding="utf-8"))
        offsets = set(session.get("received_offsets", []))
        offsets.add(offset)
        session["received_offsets"] = sorted(offsets)
        session_file.write_text(json.dumps(session), encoding="utf-8")
    return {"upload_id": upload_id, "offset": offset, "received": len(chunk), "next_offset": offset + len(chunk)}


@app.post("/api/uploads/{upload_id}/complete")
async def complete_chunk_upload(upload_id: str, title: str = Form(""), logo: UploadFile | None = File(default=None)) -> dict:
    session_dir = CHUNK_UPLOAD_DIR / upload_id
    session_file = session_dir / "session.json"
    part = session_dir / "source.part"
    if not session_file.exists() or not part.exists():
        raise HTTPException(status_code=404, detail="Upload session not found or expired.")
    session = json.loads(session_file.read_text(encoding="utf-8"))
    expected = list(range(0, session["size"], CHUNK_SIZE))
    if part.stat().st_size != session["size"] or set(session.get("received_offsets", [])) != set(expected):
        raise HTTPException(status_code=409, detail="Upload is incomplete; retry the missing chunks.")
    project_id_hint = str(int(time.time() * 1000))
    project_dir = settings.upload_dir / project_id_hint
    project_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(session["filename"]).suffix.lower() or ".mp4"
    source_path = project_dir / f"source{suffix}"
    part.replace(source_path)
    try:
        source_meta = validate_source(source_path)
        logo_path = None
        if logo is not None:
            if not (logo.content_type or "").startswith("image/"):
                raise HTTPException(status_code=400, detail="Logo upload must be an image file.")
            logo_path = str(project_dir / f"logo{Path(logo.filename or 'logo.png').suffix.lower() or '.png'}")
            await _save_upload(logo, Path(logo_path))
        project = db.create_project(title.strip() or Path(session["filename"]).stem, None, str(source_path), source_meta, logo_path)
        return {"project": project}
    finally:
        for path in session_dir.glob("*"):
            path.unlink(missing_ok=True)
        session_dir.rmdir()
        CHUNK_LOCKS.pop(upload_id, None)


@app.post("/api/projects")
async def create_project(
    title: str = Form(""),
    source_url: str = Form(""),
    video: UploadFile | None = File(default=None),
    logo: UploadFile | None = File(default=None),
) -> dict:
    if not source_url.strip() and video is None:
        raise HTTPException(status_code=400, detail="Provide a YouTube/direct video URL or upload a video file.")
    if source_url.strip() and video is not None:
        raise HTTPException(status_code=400, detail="Choose one input method: URL or upload.")
    project_id_hint = str(int(time.time() * 1000))
    project_dir = settings.upload_dir / project_id_hint
    project_dir.mkdir(parents=True, exist_ok=True)
    try:
        if video is not None:
            suffix = Path(video.filename or "source.mp4").suffix.lower() or ".mp4"
            source_path = project_dir / f"source{suffix}"
            await _save_upload(video, source_path)
            source_meta = validate_source(source_path)
            source_url_value = None
            default_title = Path(video.filename or "Uploaded film").stem
        else:
            source_path, source_meta = download_source(source_url.strip(), project_dir)
            source_url_value = source_url.strip()
            default_title = Path(urlparse(source_url_value).path).stem or "URL source"
        logo_path = None
        if logo is not None:
            content_type = logo.content_type or ""
            if not content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="Logo upload must be an image file.")
            logo_suffix = Path(logo.filename or "logo.png").suffix.lower() or ".png"
            logo_file = project_dir / f"logo{logo_suffix}"
            await _save_upload(logo, logo_file)
            logo_path = str(logo_file)
        project = db.create_project(title.strip() or default_title, source_url_value, str(source_path), source_meta, logo_path)
        return {"project": project}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/jobs")
def create_job(request: JobCreate) -> dict:
    project = db.get_project(request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    job = db.create_job(request.project_id, request.model_dump(exclude={"project_id"}))
    db.add_event(job["id"], "queued", "queued", "Job accepted; real processing will begin in the background.", 0.0)
    submit(job["id"])
    return {"job": job}


@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.get("status") == "running":
        raise HTTPException(status_code=409, detail="This job is already running.")
    if job.get("status") == "completed":
        raise HTTPException(status_code=409, detail="This job is already completed.")
    db.update_job(job_id, status="queued", current_stage="queued", error=None)
    db.add_event(job_id, "queued", "queued", "Resume requested; existing checkpoints will be reused where available.", 0.0)
    submit(job_id)
    return {"job": _job_payload(job_id)}


def _job_payload(job_id: str) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    artifacts = []
    for artifact in db.list_artifacts(job_id):
        artifact["download_url"] = f"/api/artifacts/{artifact['id']}/download"
        artifacts.append(artifact)
    job["events"] = db.list_events(job_id)
    job["artifacts"] = artifacts
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return {"job": _job_payload(job_id)}


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    if not db.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found.")

    async def stream():
        sent: set[str] = set()
        started = time.monotonic()
        while time.monotonic() - started < 7200:
            for event in db.list_events(job_id):
                if event["id"] in sent:
                    continue
                sent.add(event["id"])
                yield f"id: {event['id']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            current = db.get_job(job_id)
            if current and current.get("status") in {"completed", "completed_with_errors", "failed"}:
                break
            await asyncio.sleep(1)
        yield "event: close\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str):
    artifact = db.get_artifact(artifact_id)
    if not artifact or not artifact.get("verified"):
        raise HTTPException(status_code=404, detail="Verified artifact not found.")
    path = Path(artifact["path"])
    if not path.exists():
        raise HTTPException(status_code=410, detail="The local artifact is no longer available; durable storage transfer was not configured.")
    return FileResponse(path, media_type=artifact.get("mime_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream", filename=artifact["filename"])


@app.get("/api/history")
def history() -> dict:
    rows = []
    for project in db.list_projects():
        project_jobs = []
        with db.connection() as conn:
            result = conn.execute(db.text("SELECT id,status,current_stage,error,created_at,updated_at FROM jobs WHERE project_id=:project ORDER BY created_at DESC"), {"project": project["id"]}).fetchall()
            project_jobs = [dict(row._mapping) for row in result]
        project["jobs"] = project_jobs
        rows.append(project)
    return {"projects": rows}


@app.get("/manus-routes.json")
def routes_manifest():
    manifest = settings.root / "frontend" / "public" / "manus-routes.json"
    if manifest.exists():
        return JSONResponse(json.loads(manifest.read_text(encoding="utf-8")))
    return {"routes": [{"path": "/", "title": "RecapMaster AI"}]}


frontend_out = settings.root / "frontend" / "out"
if frontend_out.exists():
    app.mount("/", StaticFiles(directory=str(frontend_out), html=True), name="frontend")
else:
    @app.get("/")
    def root_fallback():
        return {"service": "RecapMaster AI", "status": "backend_ready", "message": "Start the Next.js frontend on port 3000 for the workbench."}
