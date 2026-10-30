from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from litestar.exceptions import HTTPException

from api.core.content_policy import is_private_path
from api.settings.config import settings
from omk.fs import resolved


def content_root() -> Path:
    """Вернуть абсолютный корень с контентом лаунчера."""
    return Path(settings.content_root).resolve()


def launcher_root() -> Path:
    """Вернуть корень метаданных и файлов лаунчера."""
    return content_root() / "launcher"


def launcher_files_root() -> Path:
    """Вернуть каталог файлов лаунчера."""
    return launcher_root() / "files"


def launcher_manifest_path() -> Path:
    """Вернуть путь к manifest-файлу лаунчера."""
    return launcher_root() / "manifest.json"


def instances_root() -> Path:
    """Вернуть корневой каталог игровых инстансов."""
    return content_root() / "instances"


def instance_root(instance_id: str) -> Path:
    """Вернуть каталог конкретного инстанса."""
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", instance_id):
        raise HTTPException(status_code=400, detail="Invalid instance id")
    return instances_root() / instance_id


def instance_files_root(instance_id: str) -> Path:
    """Вернуть каталог файлов конкретного инстанса."""
    return instance_root(instance_id) / "files"


def instance_manifest_path(instance_id: str) -> Path:
    """Вернуть путь к manifest конкретного инстанса."""
    return instance_root(instance_id) / "manifest.json"


def instance_config_path(instance_id: str) -> Path:
    """Вернуть путь к config конкретного инстанса."""
    return instance_root(instance_id) / "instance_config.json"


def launch_profile_path(instance_id: str) -> Path:
    """Вернуть путь к launch-profile конкретного инстанса."""
    return instance_root(instance_id) / "launch_profile.json"


def ensure_exists(path: Path, message: str) -> Path:
    """Вернуть путь или бросить HTTP 404, если путь не существует."""
    if not path.exists():
        raise HTTPException(status_code=404, detail=message)
    return path


def read_json(path: Path) -> Any:
    """Прочитать JSON (UTF-8) и вернуть распарсенные данные."""
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def safe_resolve(base: Path, relative_path: str) -> Path:
    """Безопасно разрешить относительный путь внутри заданного корня."""
    base_resolved = resolved(base)
    normalized_relative_path = relative_path.lstrip("/\\")
    candidate = resolved(base_resolved / normalized_relative_path)

    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid path") from exc

    if is_private_path(normalized_relative_path) or is_private_path(
        candidate.relative_to(base_resolved).as_posix()
    ):
        raise HTTPException(status_code=404, detail="File not found")
    return candidate
