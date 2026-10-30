from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from api.core.content_policy import is_private_path  # noqa: E402
from api.settings.content import (  # noqa: E402
    ManifestSettings,
    get_instance_config,
    get_instance_manifest_settings,
    get_launcher_manifest_settings,
    resolve_project_path,
)


def sha256_of_file(path: Path) -> str:
    """Посчитать SHA256-хеш файла."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_path(path: Path) -> str:
    """Преобразовать путь в относительный POSIX-формат."""
    return path.as_posix()


def should_ignore(relative_path: str, ignored_prefixes: list[str]) -> bool:
    """Проверить, начинается ли путь с одного из игнорируемых префиксов."""
    return is_private_path(relative_path) or any(
        relative_path.startswith(prefix) for prefix in ignored_prefixes
    )


def build_manifest(
    source_root: Path,
    ignored_prefixes: list[str],
    managed_roots: list[str],
    content_id: str,
    kind: str,
) -> dict:
    """Собрать payload манифеста для заданного source-корня."""
    files: dict[str, dict] = {}
    total_size = 0

    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue

        relative_path = normalize_path(path.relative_to(source_root))

        if relative_path == "manifest.json":
            continue

        if should_ignore(relative_path, ignored_prefixes):
            continue
        try:
            target = path.resolve().relative_to(source_root.resolve()).as_posix()
        except ValueError:
            continue
        if is_private_path(target):
            continue

        file_size = path.stat().st_size
        total_size += file_size

        files[relative_path] = {
            "sha256": sha256_of_file(path),
            "size": file_size,
        }

    return {
        "content_id": content_id,
        "kind": kind,
        "generated_at": datetime.now(UTC).isoformat(),
        "managed_roots": managed_roots,
        "total_size": total_size,
        "files": files,
    }


def get_manifest_settings(kind: str, instance_id: str | None) -> ManifestSettings:
    """Получить настройки манифеста для лаунчера или конкретного инстанса."""
    if kind == "launcher":
        return get_launcher_manifest_settings()

    if instance_id is None:
        raise RuntimeError("Instance id is required for instance manifest")

    return get_instance_manifest_settings(instance_id)


def get_ignored_paths(kind: str, instance_id: str | None) -> list[str]:
    """Получить игнорируемые префиксы путей для манифеста инстанса."""
    if kind == "launcher":
        return []

    if instance_id is None:
        raise RuntimeError("Instance id is required for instance manifest")

    config = get_instance_config(instance_id)
    ignored_paths: Any = config.get("ignored_paths", [])
    if not isinstance(ignored_paths, list):
        raise RuntimeError("instance_config.json field 'ignored_paths' must be a list")

    return [str(path) for path in ignored_paths]


def write_manifest(
    source_root: Path,
    manifest_path: Path,
    content_id: str,
    kind: str,
    managed_roots: list[str],
    ignored_paths: list[str],
) -> None:
    """Сгенерировать и сохранить JSON-манифест."""
    manifest = build_manifest(
        source_root=source_root,
        ignored_prefixes=ignored_paths,
        managed_roots=managed_roots,
        content_id=content_id,
        kind=kind,
    )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print(f"Manifest written to: {manifest_path}")
    print(f"Files: {len(manifest['files'])}")
    print(f"Total size: {manifest['total_size']} bytes")


def main() -> None:
    """Точка входа CLI для генерации манифеста."""
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["launcher", "instance"])
    parser.add_argument("instance_id", nargs="?")

    args = parser.parse_args()
    kind = str(args.kind)
    instance_id = args.instance_id
    settings = get_manifest_settings(kind, instance_id)

    write_manifest(
        source_root=resolve_project_path(settings["source_root"]),
        manifest_path=resolve_project_path(settings["manifest_path"]),
        content_id=settings["content_id"],
        kind=settings["kind"],
        managed_roots=settings["managed_roots"],
        ignored_paths=get_ignored_paths(kind, instance_id),
    )


if __name__ == "__main__":
    main()
