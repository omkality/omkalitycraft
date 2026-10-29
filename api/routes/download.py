from __future__ import annotations

from litestar import get
from litestar.response import File

from api.core.storage import (
    ensure_exists,
    instance_files_root,
    launcher_files_root,
    safe_resolve,
)


@get("/download/launcher/{file_path:path}", sync_to_thread=True)
def download_launcher_file(file_path: str) -> File:
    """Скачать файл лаунчера по относительному пути."""
    root = ensure_exists(launcher_files_root(), "Launcher files root not found")
    resolved = safe_resolve(root, file_path)
    ensure_exists(resolved, "Launcher file not found")

    return File(
        path=str(resolved),
        filename=resolved.name,
        media_type="application/octet-stream",
    )


@get("/download/instances/{instance_id:str}/{file_path:path}", sync_to_thread=True)
def download_instance_file(instance_id: str, file_path: str) -> File:
    """Скачать файл инстанса по относительному пути."""
    root = ensure_exists(
        instance_files_root(instance_id),
        f"Instance files root '{instance_id}' not found",
    )
    resolved = safe_resolve(root, file_path)
    ensure_exists(resolved, "Instance file not found")

    return File(
        path=str(resolved),
        filename=resolved.name,
        media_type="application/octet-stream",
    )
