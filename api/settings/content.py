from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, TypedDict

ContentKind = Literal["launcher", "instance"]


class ManifestSettings(TypedDict):
    content_id: str
    kind: ContentKind
    source_root: str
    manifest_path: str
    managed_roots: list[str]


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def settings_root() -> Path:
    return Path(__file__).resolve().parent


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise RuntimeError(f"Settings file must contain a JSON object: {path}")

    return data


def resolve_project_path(path: str) -> Path:
    return (get_project_root() / path).resolve()


def get_launcher_manifest_settings() -> ManifestSettings:
    return read_json(settings_root() / "launcher" / "manifest.json")  # type: ignore[return-value]


def get_instance_settings_root(instance_id: str) -> Path:
    return settings_root() / "instances" / instance_id


def get_instance_manifest_settings(instance_id: str) -> ManifestSettings:
    return read_json(get_instance_settings_root(instance_id) / "manifest.json")  # type: ignore[return-value]


def get_instance_config(instance_id: str) -> dict[str, Any]:
    return read_json(get_instance_settings_root(instance_id) / "instance_config.json")


def get_launch_profile(instance_id: str) -> dict[str, Any]:
    return read_json(get_instance_settings_root(instance_id) / "launch_profile.json")
