from __future__ import annotations

from litestar import get

from api.core.storage import (
    ensure_exists,
    instance_config_path,
    instance_manifest_path,
    instances_root,
    launch_profile_path,
    read_json,
)


@get("/instances", sync_to_thread=True)
def list_instances() -> list[dict]:
    """Вернуть список инстансов с краткими метаданными."""
    root = instances_root()
    if not root.exists():
        return []

    result: list[dict] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue

        manifest_file = entry / "manifest.json"
        config_file = entry / "instance_config.json"
        if not manifest_file.exists():
            continue

        manifest = read_json(manifest_file)
        config = read_json(config_file) if config_file.exists() else {}
        result.append(
            {
                "id": entry.name,
                "name": config.get("display_name", entry.name),
                "description": config.get("description", ""),
                "manifest_generated_at": manifest.get("generated_at"),
                "files_count": len(manifest.get("files", {})),
                "total_size": manifest.get("total_size", 0),
            }
        )
    return result


@get("/instances/{instance_id:str}/manifest", sync_to_thread=True)
def get_instance_manifest(instance_id: str) -> dict:
    """Вернуть raw-манифест конкретного инстанса."""
    path = ensure_exists(
        instance_manifest_path(instance_id),
        f"Instance manifest '{instance_id}' not found",
    )
    return read_json(path)


@get("/instances/{instance_id:str}/config", sync_to_thread=True)
def get_instance_config(instance_id: str) -> dict:
    """Вернуть raw-конфиг конкретного инстанса."""
    path = ensure_exists(
        instance_config_path(instance_id),
        f"Instance config '{instance_id}' not found",
    )
    return read_json(path)


@get("/instances/{instance_id:str}/launch-profile", sync_to_thread=True)
def get_launch_profile(instance_id: str) -> dict:
    """Вернуть raw-launch-profile конкретного инстанса."""
    path = ensure_exists(
        launch_profile_path(instance_id),
        f"Launch profile '{instance_id}' not found",
    )
    return read_json(path)
