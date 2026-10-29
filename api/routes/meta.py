from __future__ import annotations

from litestar import get
from litestar.response import Redirect

from api.core.project import get_project_info
from api.core.storage import content_root, instances_root
from api.settings.config import settings


@get("/", sync_to_thread=True)
def docs_redirect() -> Redirect:
    """Перенаправить корневой endpoint на Swagger-документацию."""
    return Redirect("/docs")


@get("/version", sync_to_thread=True)
def version() -> dict[str, str]:
    """Вернуть метаданные проекта из `pyproject.toml`."""
    project_info = get_project_info()
    return {
        "name": project_info["name"],
        "version": project_info["version"],
        "description": project_info["description"],
    }


@get("/health", sync_to_thread=True)
def health() -> dict[str, object]:
    """Вернуть базовый health-check API и диагностику контент-корня."""
    root = content_root()
    instances = instances_root()

    instances_count = 0
    if instances.exists():
        instances_count = len([p for p in instances.iterdir() if p.is_dir()])

    return {
        "status": "ok",
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "content_root": str(root),
        "instances_count": instances_count,
    }
