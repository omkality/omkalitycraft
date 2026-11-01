from typing import Annotated

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerStatusTarget(BaseModel):
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.:-]+$")
    port: int = Field(default=25565, ge=1, le=65535, strict=True)


class Settings(BaseSettings):
    """CDN settings; authentication is delegated to Drasl."""

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    workers_num: int = 1
    content_root: str = "data/content"
    client_reports_root: str | None = None
    client_reports_auth_url: str | None = None
    server_status_cache_seconds: int = Field(default=15, ge=1, le=300)
    server_status_timeout_seconds: float = Field(default=2, ge=0.1, le=5)
    server_status_targets: dict[
        Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")], ServerStatusTarget
    ] = Field(default_factory=dict, max_length=8)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
