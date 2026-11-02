"""Validated API process entry point shared by native and container launches."""

import os
import sys
from typing import TYPE_CHECKING

from pydantic import ValidationError
from pydantic_settings import SettingsError

if TYPE_CHECKING:
    from api.settings.config import Settings


def server_command(settings: Settings) -> list[str]:
    return [
        sys.executable,
        "-m",
        "granian",
        "--interface",
        "asgi",
        "api.app:app",
        "--host",
        settings.api_host,
        "--port",
        str(settings.api_port),
        "--workers",
        str(settings.workers_num),
    ]


def main() -> int:
    try:
        # Import here so a bad .env is rejected before the ASGI app starts and
        # without echoing supplied values or a settings traceback into logs.
        from api.settings.config import settings  # noqa: PLC0415
    except ValidationError, SettingsError:
        print("Invalid API configuration; check environment and .env.", file=sys.stderr)
        return 2
    command = server_command(settings)
    os.execv(command[0], command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
