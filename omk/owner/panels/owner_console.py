"""Small fixed owner command palette using the existing private loopback RCON."""

import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from omk.owner.admin import load_operator_config
from omk.owner.owner_result import ServerId

COMMANDS = {"players": "list uuids", "tps": "forge tps", "save": "save-all flush"}


class ConsoleResult(BaseModel):
    """Describe the result returned by an owner console operation."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    action: Literal["owner.console"] = "owner.console"
    server_id: ServerId
    command: Literal["players", "tps", "save"]
    ok: bool
    effect: Literal["none", "unknown"]
    output: str = Field(default="", max_length=8192)
    error: Literal["invalid_configuration", "console_unavailable"] | None = None


def run(path, server, action, *, confirmed=False):
    effect = "none"
    try:
        config = load_operator_config(path)
        if server not in config.servers or action not in COMMANDS:
            raise ValueError("Unknown console action or server")
        if action == "save" and not confirmed:
            raise ValueError("Explicit confirmation required for save")
        from omk.labs.recovery.recovery_console import command  # noqa: PLC0415
        from omk.owner.admin_maintenance import credential  # noqa: PLC0415

        endpoint, password = credential(config, server)
    except Exception:
        return ConsoleResult(
            server_id=server,
            command=action,
            ok=False,
            effect=effect,
            error="invalid_configuration",
        ).model_dump(mode="json")
    try:
        # From this point a save may have reached the server, even on lost reply.
        effect = "unknown" if action == "save" else "none"
        output = command(endpoint, password, COMMANDS[action])
        if len(output) > 8192 or password in output:
            raise ValueError("Invalid console output")
        # Terminal escape sequences must never be interpreted by the UI.
        output = "".join(
            char
            for char in output
            if char == "\n" or not unicodedata.category(char).startswith("C")
        )
        return ConsoleResult(
            server_id=server,
            command=action,
            ok=True,
            effect=effect,
            output=output,
        ).model_dump(mode="json")
    except Exception:
        return ConsoleResult(
            server_id=server,
            command=action,
            ok=False,
            effect=effect,
            error="console_unavailable",
        ).model_dump(mode="json")
