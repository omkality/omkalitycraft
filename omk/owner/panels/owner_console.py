"""Small fixed owner command palette using the existing private loopback RCON."""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from omk.owner.admin import (
    _client,
    _credential,
    invitation_summary,
    load_operator_config,
)
from omk.owner.owner_result import ServerId

COMMANDS = {"players": "list uuids", "tps": "forge tps", "save": "save-all flush"}
VIEWS = {"roster", "invites"}


class ConsoleResult(BaseModel):
    """Describe the result returned by an owner console operation."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    action: Literal["owner.console"] = "owner.console"
    server_id: ServerId
    command: Literal["players", "roster", "invites", "tps", "save"]
    ok: bool
    effect: Literal["none", "unknown"]
    output: str = Field(default="", max_length=8192)
    error: Literal["invalid_configuration", "console_unavailable"] | None = None


def _roster(config, online):
    values = _client(config).request(
        "GET", "/drasl/api/v3/users", token=_credential(config)
    )
    if not isinstance(values, list) or len(values) > 1000:
        raise ValueError("Invalid player inventory")
    names = set()
    for user in values:
        players = user.get("players")
        if not isinstance(players, list):
            raise ValueError("Invalid account players")
        for row in players:
            name = row.get("name")
            if not isinstance(name, str) or not re.fullmatch(
                r"[A-Za-z0-9_]{1,16}", name
            ):
                raise ValueError("Invalid player name")
            names.add(name)
    names.update(online or ())
    if not names:
        return "Никто пока не зарегистрировался."
    rows = []
    for name in sorted(names, key=str.casefold):
        state = (
            "Статус неизвестен"
            if online is None
            else ("В игре" if name in online else "Не в игре")
        )
        rows.append(f"{name:<16}  {state}")
    return "\n".join(rows)


def _view(config, action, server):
    if action == "invites":
        entries = invitation_summary(config)
        return (
            "\n".join(
                f"{reference}   {prefix}…   {created[:10]}"
                for reference, prefix, created in entries
            )
            if entries
            else "Активных приглашений нет."
        )
    from omk.labs.recovery.recovery_console import (  # noqa: PLC0415
        command,
        online_players,
    )
    from omk.owner.admin_maintenance import credential  # noqa: PLC0415

    try:
        endpoint, password = credential(config, server)
        online = set(
            online_players(command(endpoint, password, COMMANDS["players"])).values()
        )
    except ValueError, RuntimeError, OSError:
        online = None
    return _roster(config, online)


def run(path, server, action, *, confirmed=False):
    """Return fixed private owner console output or a project account view."""
    effect = "none"
    try:
        config = load_operator_config(path)
        if (
            server not in config.servers
            or (action not in COMMANDS
            and action not in VIEWS)
        ):
            raise ValueError("Unknown console action or server")
        if action == "save" and not confirmed:
            raise ValueError("Explicit confirmation required for save")
        from omk.labs.recovery.recovery_console import command  # noqa: PLC0415
        from omk.owner.admin_maintenance import credential  # noqa: PLC0415

        if action not in VIEWS:
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
        output = (
            _view(config, action, server)
            if action in VIEWS
            else command(endpoint, password, COMMANDS[action])
        )
        if len(output) > 8192 or (action not in VIEWS and password in output):
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
