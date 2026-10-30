from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CDN settings; authentication is delegated to Drasl."""

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    workers_num: int = 1
    content_root: str = "data/content"
    client_reports_root: str | None = None
    client_reports_auth_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
