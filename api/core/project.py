from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TypedDict


class ProjectInfo(TypedDict):
    """Типизированное представление метаданных проекта."""

    name: str
    version: str
    description: str


def get_project_root() -> Path:
    """Найти корень репозитория по ближайшему `pyproject.toml`."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("Project root with pyproject.toml was not found")


def get_project_info() -> ProjectInfo:
    """Прочитать имя, версию и описание проекта из `pyproject.toml`."""
    pyproject_path = get_project_root() / "pyproject.toml"

    with pyproject_path.open("rb") as file:
        data = tomllib.load(file)

    project = data["project"]
    return {
        "name": str(project["name"]),
        "version": str(project["version"]),
        "description": str(project["description"]),
    }
