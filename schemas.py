from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .config import PLATFORMS, QUALITY


class JobOptions(BaseModel):
    language: str = "my"
    length: Literal["short", "standard", "full"] = "standard"
    tone: Literal["engaging", "dramatic", "humorous", "analytical"] = "engaging"
    spoiler: bool = False
    quality: Literal["draft", "standard", "high", "ultra", "cinema"] = "high"
    platforms: list[str] = Field(default_factory=lambda: ["youtube", "tiktok"], min_length=1)

    @field_validator("platforms")
    @classmethod
    def valid_platforms(cls, values: list[str]) -> list[str]:
        unique = list(dict.fromkeys(values))
        invalid = [value for value in unique if value not in PLATFORMS]
        if invalid:
            raise ValueError(f"Unsupported platforms: {', '.join(invalid)}")
        return unique


class JobCreate(JobOptions):
    project_id: str


class ProjectResponse(BaseModel):
    id: str
    title: str
    source_url: str | None = None
    source_path: str | None = None
    source_meta: dict = Field(default_factory=dict)
    created_at: str


class ArtifactResponse(BaseModel):
    id: str
    kind: str
    platform: str | None = None
    filename: str
    mime_type: str
    size_bytes: int
    metadata: dict = Field(default_factory=dict)
    verified: bool
    download_url: str


class JobResponse(BaseModel):
    id: str
    project_id: str
    status: str
    current_stage: str | None = None
    error: str | None = None
    options: dict = Field(default_factory=dict)
    events: list[dict] = Field(default_factory=list)
    artifacts: list[ArtifactResponse] = Field(default_factory=list)
