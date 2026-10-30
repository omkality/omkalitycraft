"""Stable path identity, including Windows' optional extended-path namespace."""

from pathlib import Path


def strip_windows_namespace(value: str) -> str:
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    if value.startswith("\\\\?\\"):
        return value[4:]
    return value


def resolved(path: Path) -> Path:
    # On Windows concurrent directory creation/rename can make realpath return
    # either C:\... or \\?\C:\... for the same location. Compare one namespace.
    return Path(strip_windows_namespace(str(path.resolve())))
