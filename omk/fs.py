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


def regular(path: Path, root: Path) -> bool:
    """Reject symlinks/junctions in every component, including inside root."""
    try:
        relative = path.relative_to(root)
        current = root
        for part in ("", *relative.parts):
            current = current / part
            if current.is_symlink() or current.is_junction():
                return False
        return path.is_file() and resolved(path).is_relative_to(resolved(root))
    except OSError, ValueError:
        return False
