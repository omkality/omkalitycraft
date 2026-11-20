"""Fixtures piped to the disposable API image by the container smoke."""

import json
import sys
from importlib.util import find_spec
from pathlib import Path
from urllib.request import urlopen


def main(mode: str) -> object:
    """Read one container property without dumping its environment."""
    if mode == "health":
        with urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
            return json.load(response)
    if mode == "pid1":
        return Path("/proc/1/cmdline").read_bytes().decode().split(chr(0))
    if mode == "settings":
        from api.settings.config import settings  # noqa: PLC0415

        return [
            settings.workers_num,
            settings.api_requests_per_second,
            settings.client_reports_prune_interval_seconds,
            settings.server_status_cache_seconds,
            settings.server_status_timeout_seconds,
            settings.server_status_targets["synthetic"].port,
        ]
    if mode == "private":
        return all(
            not Path(path).exists()
            for path in (
                ".env",
                ".omk-admin",
                ".local",
                ".git",
                "launcher",
                "test-marker.key",
                "test-marker.pem",
                "test-marker.db",
                "api/settings/test-marker.key",
                "api/settings/test-marker.pem",
                "api/settings/test-marker.db",
                "api/settings/test-marker.json",
            )
        ) and all(
            find_spec(package) is None
            for package in (
                "PySide6",
                "testcontainers",
                "pytest",
                "ruff",
                "mypy",
            )
        )
    raise ValueError("Unknown API fixture probe")


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1])))
