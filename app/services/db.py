"""Cliente Supabase para persistencia"""
from supabase import create_client, Client
from loguru import logger
from typing import Any

from app.core.config import settings


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
