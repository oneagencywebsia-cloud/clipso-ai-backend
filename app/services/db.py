"""Cliente Supabase para persistencia"""
from __future__ import annotations

import time
from supabase import create_client, Client
from loguru import logger
from typing import Any, Literal

from app.core.config import settings

JobStatus = Literal[
    "queued", "downloading", "transcribing", "analyzing",
    "planning", "rendering", "uploading", "completed", "failed",
]


class SupabaseClient:
    def __init__(self):
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = create_client(
                settings.supabase_url,
                settings.supabase_key
            )
        return self._client

    # ---------- Projects ----------
    def create_project(self, user_id: str, name: str, metadata: dict | None = None) -> dict:
        result = self.client.table("clipso_projects").insert({
            "user_id": user_id,
            "name": name,
            "status": "draft",
            "metadata": metadata or {}
        }).execute()
        logger.info(f"Project creado: {result.data[0]['id']}")
        return result.data[0]

    def get_project(self, project_id: str, user_id: str) -> dict | None:
        result = (
            self.client.table("clipso_projects")
            .select("*")
            .eq("id", project_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return result.data

    def list_user_projects(self, user_id: str, limit: int = 50) -> list[dict]:
        result = (
            self.client.table("clipso_projects")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def update_project(self, project_id: str, data: dict) -> dict:
        result = (
            self.client.table("clipso_projects")
            .update(data)
            .eq("id", project_id)
            .execute()
        )
        return result.data[0] if result.data else {}

    # ---------- Jobs ----------
    def create_job(
        self,
        project_id: str,
        user_id: str,
        input_keys: list[str],
        preferences: str | None = None
    ) -> dict:
        result = self.client.table("clipso_jobs").insert({
            "project_id": project_id,
            "user_id": user_id,
            "status": "queued",
            "input_keys": input_keys,
            "preferences": preferences,
            "progress": 0
        }).execute()
        logger.info(f"Job creado: {result.data[0]['id']}")
        return result.data[0]

    def get_job(self, job_id: str) -> dict | None:
        result = (
            self.client.table("clipso_jobs")
            .select("*")
            .eq("id", job_id)
            .single()
            .execute()
        )
        return result.data

    def update_job(self, job_id: str, data: dict) -> dict:
        result = (
            self.client.table("clipso_jobs")
            .update(data)
            .eq("id", job_id)
            .execute()
        )
        return result.data[0] if result.data else {}

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: int,
        timeline_json: dict | None = None,
        output_url: str | None = None,
        error_message: str | None = None,
    ) -> dict:
        """
        Actualiza el estado de un job en tiempo real.
        Supabase Realtime propaga el cambio a todos los clientes suscritos
        en < 100ms via WebSocket (canal postgres_changes).

        Llamar entre cada paso del pipeline:
            db.update_job_status(job_id, "transcribing", 22)
            db.update_job_status(job_id, "completed", 100, timeline_json=tl.model_dump())
        """
        payload: dict[str, Any] = {
            "status":     status,
            "progress":   max(0, min(100, progress)),
            "updated_at": "now()",
        }
        if timeline_json is not None:
            payload["timeline_json"] = timeline_json
        if output_url is not None:
            payload["output_url"] = output_url
        if error_message is not None:
            payload["error_message"] = error_message
        if status == "completed":
            payload["completed_at"] = "now()"

        try:
            result = (
                self.client.table("clipso_jobs")
                .update(payload)
                .eq("id", job_id)
                .execute()
            )
            row = result.data[0] if result.data else {}
            logger.info(f"Job {job_id} → {status} ({progress}%)")
            return row
        except Exception as exc:
            # No propagamos: el pipeline no debe romperse por un fallo de DB
            logger.error(f"update_job_status failed for {job_id}: {exc}")
            return {}

    def list_user_jobs(self, user_id: str, limit: int = 50) -> list[dict]:
        result = (
            self.client.table("clipso_jobs")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []


# Singleton
db = SupabaseClient()
