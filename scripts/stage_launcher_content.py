from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from api.settings.content import (  # noqa: E402
    get_instance_config,
    get_instance_manifest_settings,
    get_launch_profile,
    get_launcher_manifest_settings,
    resolve_project_path,
)
from scripts.generate_manifest import write_manifest  # noqa: E402


def copy_path(source: Path, destination: Path) -> None:
    """Скопировать файл или каталог, сохраняя метаданные где возможно."""
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_existing_paths(
    source_root: Path, destination_root: Path, relative_paths: list[str]
) -> None:
    """Скопировать указанные относительные пути, которые существуют в source-корне."""
    for relative_path in relative_paths:
        normalized = relative_path.rstrip("/")
        source = source_root / normalized
        if not source.exists():
            print(f"Skip missing path: {source}")
            continue

        copy_path(source, destination_root / normalized)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Записать JSON-payload в UTF-8 с форматированием."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)
        file.write("\n")


def get_ignored_paths(instance_config: dict[str, Any]) -> list[str]:
    """Извлечь список игнорируемых путей из конфигурации инстанса."""
    ignored_paths = instance_config.get("ignored_paths", [])
    if not isinstance(ignored_paths, list):
        raise RuntimeError("instance_config.json field 'ignored_paths' must be a list")

    return [str(path) for path in ignored_paths]


def validate_classpath(source_root: Path, launch_profile: dict[str, Any]) -> None:
    """Проверить, что все classpath-элементы существуют в source-дереве."""
    classpath = launch_profile.get("classpath", [])
    if not isinstance(classpath, list):
        raise RuntimeError("launch_profile.json field 'classpath' must be a list")

    missing = [
        str(path) for path in classpath if not (source_root / str(path)).exists()
    ]
    if missing:
        missing_text = "\n".join(f"- {path}" for path in missing)
        raise RuntimeError(
            f"Launch profile contains missing classpath entries:\n{missing_text}"
        )


def parse_args() -> argparse.Namespace:
    """Разобрать аргументы командной строки для staging-скрипта."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--instance-id", default="divinejourney2")
    return parser.parse_args()


def main() -> None:
    """Точка входа CLI для сборки staged-контента лаунчера."""
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    instance_id = str(args.instance_id)

    launcher_manifest_settings = get_launcher_manifest_settings()
    instance_manifest_settings = get_instance_manifest_settings(instance_id)
    instance_config = get_instance_config(instance_id)
    launch_profile = get_launch_profile(instance_id)

    launcher_files_root = resolve_project_path(
        launcher_manifest_settings["source_root"]
    )
    instance_files_root = resolve_project_path(
        instance_manifest_settings["source_root"]
    )
    instance_root = resolve_project_path(
        instance_manifest_settings["manifest_path"]
    ).parent
    client_launcher_path = PROJECT_ROOT / "launcher" / "app.py"

    if not source_root.exists():
        raise RuntimeError(f"Source launcher root not found: {source_root}")

    validate_classpath(source_root, launch_profile)

    print(f"Source launcher root: {source_root}")
    print(f"Launcher files root: {launcher_files_root}")
    print(f"Instance files root: {instance_files_root}")

    launcher_paths = [
        path
        for path in launcher_manifest_settings["managed_roots"]
        if path != "launcher.py"
    ]
    copy_existing_paths(source_root, launcher_files_root, launcher_paths)
    copy_path(client_launcher_path, launcher_files_root / "launcher.py")

    copy_existing_paths(
        source_root / "instances" / instance_id,
        instance_files_root,
        instance_manifest_settings["managed_roots"],
    )

    write_json(instance_root / "instance_config.json", instance_config)
    write_json(instance_root / "launch_profile.json", launch_profile)

    write_manifest(
        source_root=resolve_project_path(launcher_manifest_settings["source_root"]),
        manifest_path=resolve_project_path(launcher_manifest_settings["manifest_path"]),
        content_id=launcher_manifest_settings["content_id"],
        kind=launcher_manifest_settings["kind"],
        managed_roots=launcher_manifest_settings["managed_roots"],
        ignored_paths=[],
    )
    write_manifest(
        source_root=resolve_project_path(instance_manifest_settings["source_root"]),
        manifest_path=resolve_project_path(instance_manifest_settings["manifest_path"]),
        content_id=instance_manifest_settings["content_id"],
        kind=instance_manifest_settings["kind"],
        managed_roots=instance_manifest_settings["managed_roots"],
        ignored_paths=get_ignored_paths(instance_config),
    )


if __name__ == "__main__":
    main()
