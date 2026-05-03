"""Pydantic schemas — validación de request/response"""
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime


# ---------- Upload ----------
class PresignedUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field("video/mp4")
    size_bytes: int = Field(..., gt=0)


class PresignedUploadResponse(BaseModel):
    upload_url: str
    key: str
    expires_in: int


# ---------- Projects ----------
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class ProjectResponse(BaseModel):
    id: str
    user_id: str
    name: str
    status: str
    metadata: dict[str, Any] = {}
    created_at: datetime | None = None


# ---------- Jobs ----------
class JobCreateRequest(BaseModel):
    project_id: str
    input_keys: list[str] = Field(..., min_length=1)
    preferences: str | None = None
    target_resolution: str = Field("1080p", pattern="^(720p|1080p|4k)$")
    target_fps: int = Field(30, ge=24, le=60)


class JobResponse(BaseModel):
    id: str
    project_id: str
    user_id: str
    status: str
    progress: int = 0
    input_keys: list[str]
    output_key: str | None = None
    preferences: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class JobFeedback(BaseModel):
    instructions: str = Field(..., min_length=1, max_length=2000)


# ---------- Health ----------
class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str
    environment: str
