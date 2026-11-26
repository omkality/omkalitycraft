"""Keep bounded start and end times for owner operations."""

import sys
from pathlib import Path

from omk.owner.admin import AdminError, OperatorConfig, _read_json, _write_private

WINDOW_LIMIT = 384
_FOLDERS = {
    "hourly_backup": "hourly-backups",
    "world_reset": "world-reset",
    "server_start": "server-starts",
}


def _path(config: OperatorConfig, server: str, operation: str) -> Path:
    if server not in config.servers or operation not in _FOLDERS:
        raise AdminError("Unknown owner operation timing history")
    return config.private / _FOLDERS[operation] / server / "capture-windows.json"


def read_windows(
    config: OperatorConfig, server: str, operation: str
) -> list[list[int | float]] | None:
    """Read the retained Unix-time intervals, or return None if not recorded."""
    path = _path(config, server, operation)
    if not path.exists() and not path.is_symlink():
        return None
    data = _read_json(path, config.private)
    windows = data.get("windows")
    if (
        data.get("schema") != 1
        or not isinstance(windows, list)
        or len(windows) > WINDOW_LIMIT
    ):
        raise AdminError("Invalid owner operation timing history")
    for window in windows:
        if (
            not isinstance(window, list)
            or len(window) != 2
            or any(type(stamp) not in {int, float} for stamp in window)
            or not 0 < window[0] < window[1] < float("inf")
        ):
            raise AdminError("Invalid owner operation timing history")
    return windows


def record_window(
    config: OperatorConfig, server: str, operation: str, start: float, end: float
) -> None:
    """Append an interval under the caller's owner lock without changing its result."""
    if not 0 < start < end < float("inf"):
        return
    try:
        windows = read_windows(config, server, operation) or []
        windows.append([start, end])
        _write_private(
            _path(config, server, operation),
            config.private,
            {"schema": 1, "windows": windows[-WINDOW_LIMIT:]},
        )
    except AdminError, OSError, ValueError:
        print(f"Could not record {operation.replace('_', ' ')} timing", file=sys.stderr)
