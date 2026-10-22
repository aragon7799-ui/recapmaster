from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .config import settings


def _engine_parts(url: str) -> tuple[str, dict]:
    normalized = "mysql+pymysql://" + url[len("mysql://") :] if url.startswith("mysql://") else url
    parsed = make_url(normalized)
    connect_args: dict = {}
    if parsed.drivername == "mysql+pymysql":
        query = dict(parsed.query)
        ssl_value = query.pop("ssl", None)
        if ssl_value is not None:
            # The managed DSN carries Node-style JSON (`rejectUnauthorized`),
            # while PyMySQL accepts a dict with verify_mode/check_hostname.
            try:
                ssl_options = json.loads(ssl_value) if isinstance(ssl_value, str) else ssl_value
            except json.JSONDecodeError:
                ssl_options = {}
            reject = bool((ssl_options or {}).get("rejectUnauthorized", True))
            connect_args["ssl"] = {"check_hostname": reject, "verify_mode": "required" if reject else "none"}
        parsed = parsed.set(query=query)
    elif parsed.drivername == "sqlite":
        connect_args["check_same_thread"] = False
    return str(parsed), connect_args


_database_url, _connect_args = _engine_parts(settings.database_url)
engine = create_engine(_database_url, future=True, pool_pre_ping=True, connect_args=_connect_args)
database_status = {"mode": "configured", "configured_driver": _database_url.split(":", 1)[0], "error": None}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize() -> None:
    statements = [
        """CREATE TABLE IF NOT EXISTS projects (
            id VARCHAR(64) PRIMARY KEY, title VARCHAR(255) NOT NULL, source_url TEXT,
            source_path TEXT, logo_path TEXT, source_meta_json TEXT NOT NULL,
            created_at VARCHAR(64) NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS jobs (
            id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
            options_json TEXT NOT NULL, current_stage VARCHAR(64), error TEXT,
            created_at VARCHAR(64) NOT NULL, updated_at VARCHAR(64) NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS events (
            id VARCHAR(64) PRIMARY KEY, job_id VARCHAR(64) NOT NULL, stage VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL, message TEXT NOT NULL, progress DOUBLE NOT NULL,
            platform VARCHAR(64), details_json TEXT NOT NULL, created_at VARCHAR(64) NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS artifacts (
            id VARCHAR(64) PRIMARY KEY, job_id VARCHAR(64) NOT NULL, project_id VARCHAR(64) NOT NULL,
            kind VARCHAR(64) NOT NULL, platform VARCHAR(64), path TEXT NOT NULL, stable_url TEXT,
            filename VARCHAR(255) NOT NULL, mime_type VARCHAR(128) NOT NULL, size_bytes BIGINT NOT NULL,
            metadata_json TEXT NOT NULL, verified BOOLEAN NOT NULL, created_at VARCHAR(64) NOT NULL
        )""",
    ]
    global engine, database_status
    try:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
    except Exception as exc:
        if _database_url.startswith("sqlite:"):
            raise
        # Keep Preview usable for honest smoke testing without claiming that
        # the configured managed database is healthy or durable.
        fallback_url = f"sqlite:///{settings.data_dir / 'recapmaster-fallback.sqlite3'}"
        engine = create_engine(fallback_url, future=True, pool_pre_ping=True, connect_args={"check_same_thread": False})
        database_status = {"mode": "sqlite_fallback", "configured_driver": _database_url.split(":", 1)[0], "error": str(exc)}
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))


@contextmanager
def connection():
    with engine.begin() as conn:
        yield conn


def _decode(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    value = dict(row._mapping)
    for key in ("source_meta_json", "options_json", "details_json", "metadata_json"):
        if key in value and value[key]:
            try:
                value[key[:-5] if key.endswith("_json") else key] = json.loads(value[key])
            except json.JSONDecodeError:
                value[key[:-5] if key.endswith("_json") else key] = {}
    return value


def create_project(title: str, source_url: str | None, source_path: str | None, source_meta: dict[str, Any], logo_path: str | None = None) -> dict[str, Any]:
    project_id = str(uuid.uuid4())
    timestamp = now_iso()
    with connection() as conn:
        conn.execute(text("INSERT INTO projects (id,title,source_url,source_path,logo_path,source_meta_json,created_at) VALUES (:id,:title,:url,:path,:logo,:meta,:created)"), {
            "id": project_id, "title": title, "url": source_url, "path": source_path, "logo": logo_path,
            "meta": json.dumps(source_meta, ensure_ascii=False), "created": timestamp,
        })
    return get_project(project_id) or {"id": project_id}


def get_project(project_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(text("SELECT * FROM projects WHERE id=:id"), {"id": project_id}).first()
    return _decode(row)


def list_projects(limit: int = 30) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(text("SELECT * FROM projects ORDER BY created_at DESC LIMIT :limit"), {"limit": limit}).fetchall()
    return [_decode(row) for row in rows if row]


def create_job(project_id: str, options: dict[str, Any]) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    timestamp = now_iso()
    with connection() as conn:
        conn.execute(text("INSERT INTO jobs (id,project_id,status,options_json,current_stage,error,created_at,updated_at) VALUES (:id,:project,:status,:options,:stage,:error,:created,:updated)"), {
            "id": job_id, "project": project_id, "status": "queued", "options": json.dumps(options, ensure_ascii=False),
            "stage": "queued", "error": None, "created": timestamp, "updated": timestamp,
        })
    return get_job(job_id) or {"id": job_id}


def get_job(job_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(text("SELECT * FROM jobs WHERE id=:id"), {"id": job_id}).first()
    return _decode(row)


def update_job(job_id: str, **fields: Any) -> None:
    allowed = {"status", "current_stage", "error"}
    values = {key: value for key, value in fields.items() if key in allowed}
    if not values:
        return
    values["updated_at"] = now_iso()
    setters = ", ".join(f"{key}=:{key}" for key in values)
    values["id"] = job_id
    with connection() as conn:
        conn.execute(text(f"UPDATE jobs SET {setters} WHERE id=:id"), values)


def add_event(job_id: str, stage: str, status: str, message: str, progress: float, platform: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    event_id = str(uuid.uuid4())
    with connection() as conn:
        conn.execute(text("INSERT INTO events (id,job_id,stage,status,message,progress,platform,details_json,created_at) VALUES (:id,:job,:stage,:status,:message,:progress,:platform,:details,:created)"), {
            "id": event_id, "job": job_id, "stage": stage, "status": status, "message": message,
            "progress": max(0.0, min(1.0, progress)), "platform": platform,
            "details": json.dumps(details or {}, ensure_ascii=False), "created": now_iso(),
        })
    return {"id": event_id, "job_id": job_id, "stage": stage, "status": status, "message": message, "progress": progress, "platform": platform, "details": details or {}}


def list_events(job_id: str, after_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM events WHERE job_id=:job"
    params: dict[str, Any] = {"job": job_id}
    if after_id:
        query += " AND created_at > (SELECT created_at FROM events WHERE id=:after_id)"
        params["after_id"] = after_id
    query += " ORDER BY created_at ASC"
    with connection() as conn:
        rows = conn.execute(text(query), params).fetchall()
    return [_decode(row) for row in rows if row]


def add_artifact(job_id: str, project_id: str, kind: str, platform: str | None, path: str, filename: str, mime_type: str, size_bytes: int, metadata: dict[str, Any], verified: bool) -> dict[str, Any]:
    artifact_id = str(uuid.uuid4())
    with connection() as conn:
        conn.execute(text("INSERT INTO artifacts (id,job_id,project_id,kind,platform,path,stable_url,filename,mime_type,size_bytes,metadata_json,verified,created_at) VALUES (:id,:job,:project,:kind,:platform,:path,:stable,:filename,:mime,:size,:metadata,:verified,:created)"), {
            "id": artifact_id, "job": job_id, "project": project_id, "kind": kind, "platform": platform,
            "path": path, "stable": None, "filename": filename, "mime": mime_type, "size": size_bytes,
            "metadata": json.dumps(metadata, ensure_ascii=False), "verified": verified, "created": now_iso(),
        })
    return get_artifact(artifact_id) or {"id": artifact_id}


def get_artifact(artifact_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(text("SELECT * FROM artifacts WHERE id=:id"), {"id": artifact_id}).first()
    return _decode(row)


def list_artifacts(job_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(text("SELECT * FROM artifacts WHERE job_id=:job ORDER BY created_at ASC"), {"job": job_id}).fetchall()
    return [_decode(row) for row in rows if row]
