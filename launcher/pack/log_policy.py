"""Versioned Java logging adapter; unrelated packs keep their declared configuration."""

import os
from pathlib import Path
from string import Template

from omk.diagnostics import prune_native_archives, prune_reports
from omk.fs import resolved

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def forge_log_settings(environment=None) -> dict[str, int]:
    env = os.environ if environment is None else environment
    settings = {}
    for suffix, default, maximum in (("MIB", 8, 64), ("FILES", 3, 10)):
        name = "OMK_FORGE_LOG_" + suffix
        raw = env.get(name, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 2
            or not 1 <= int(raw) <= maximum
        ):
            raise ValueError("Invalid " + name)
        settings[suffix.lower()] = int(raw)
    return settings


_FORGE_112 = Template((ASSETS / "forge-1.12.2-log4j2.xml").read_text(encoding="utf-8"))

FORGE_112 = _FORGE_112.substitute(forge_log_settings({}))


def prepare_logging(
    minecraft: str, directory: Path, *, environment=None
) -> Path | None:
    if minecraft != "1.12.2":
        return None
    text = _FORGE_112.substitute(forge_log_settings(environment))
    if resolved(directory) != directory:
        raise OSError("Linked logging configuration directory")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "forge-1.12.2.xml"
    if path.is_symlink() or path.is_junction() or directory.resolve() != directory:
        raise OSError("Linked logging configuration")
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    return path


def prune_game_logs(root: Path, folder: Path):
    """Called only before launch or after the owned process has stopped."""
    prune_reports(root, folder / "crash-reports")
    prune_reports(root, folder, jvm=True)
    prune_native_archives(root, folder / "logs")
