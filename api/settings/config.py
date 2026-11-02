from ipaddress import ip_address
from typing import Annotated

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerStatusTarget(BaseModel):
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.:-]+$")
    port: int = Field(default=25565, ge=1, le=65535, strict=True)


class Settings(BaseSettings):
    """CDN settings; authentication is delegated to Drasl."""

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    workers_num: int = Field(default=1, ge=1, le=32)
    api_requests_per_second: int = Field(default=128, ge=1, le=10000)
    client_reports_prune_interval_seconds: int = Field(default=3600, ge=60, le=86400)
    # Compose applies these limits; native launches only validate their syntax/range.
    omk_api_cpus: float = Field(default=1, ge=0.1, le=64)
    omk_api_memory_mib: int = Field(default=1024, ge=128, le=65536)
    omk_api_log_mib: int = Field(default=10, ge=1, le=1024)
    omk_api_log_files: int = Field(default=3, ge=1, le=30)
    content_root: str = "data/content"
    client_reports_root: str | None = None
    client_reports_auth_url: str | None = None
    server_status_cache_seconds: int = Field(default=15, ge=1, le=300)
    server_status_timeout_seconds: float = Field(default=2, ge=0.1, le=5)
    server_status_targets: dict[
        Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")], ServerStatusTarget
    ] = Field(default_factory=dict, max_length=8)

    @field_validator("api_host")
    @classmethod
    def valid_bind_address(cls, value: str) -> str:
        return str(ip_address(value))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )


settings = Settings()
