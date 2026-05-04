"""Configuración centralizada — lee variables de entorno"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # App
    app_name: str = "CLIPSO.AI Backend"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "https://clipso.ai",
        "https://app.clipso.ai",
        "https://one-agency-clipso-ai.94rrjd.easypanel.host"
    ]

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_jwt_secret: str = ""

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "clipso-videos"
    r2_endpoint_url: str = ""
    r2_public_url: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Redis (queue)
    redis_url: str = "redis://localhost:6379/0"

    # Upload limits
    max_upload_size_mb: int = 500
    max_video_duration_sec: int = 300

    @property
    def r2_endpoint(self) -> str:
        return self.r2_endpoint_url or f"https://{self.r2_account_id}.r2.cloudflarestorage.com"


settings = Settings()
