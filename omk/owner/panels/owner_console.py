"""Small fixed owner command palette using the existing private loopback RCON."""

import re
import unicodedata
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from omk.game.project_permanent_bans import (
    USERS,
    load as load_permanent_bans,
)
from omk.owner.admin import (
    _client,
    _credential,
    invitation_summary,
    load_operator_config,
)
from omk.owner.owner_result import ServerId

COMMANDS = {"players": "list uuids", "tps": "forge tps", "save": "save-all flush"}
VIEWS = {"roster", "permanent-bans", "invites", "player-names", "backup-status"}
MAX_PLAYER_NAMES = 1000


class InvitationEntry(BaseModel):
    """A private owner view of one unused registration code."""

    reference: str = Field(pattern=r"^[a-f0-9]{12}$")
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    date: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class ConsoleResult(BaseModel):
    """Describe the result returned by an owner console operation."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    action: Literal["owner.console"] = "owner.console"
    server_id: ServerId
    command: Literal[
        "players",
        "roster",
        "permanent-bans",
        "invites",
        "player-names",
        "tps",
        "save",
        "backup-status",
    ]
    ok: bool
    effect: Literal["none", "unknown"]
    output: str = Field(default="", max_length=MAX_PLAYER_NAMES * 17 - 1)
    error: Literal["invalid_configuration", "console_unavailable"] | None = None
    invitations: list[InvitationEntry] | None = Field(
        default=None, exclude_if=lambda rows: rows is None
    )


def _project_members(config):
    values = _client(config).request("GET", USERS, token=_credential(config))
    if not isinstance(values, list) or len(values) > 1000:
        raise ValueError("Invalid player inventory")
    _, permanent = load_permanent_bans(config.private)
    names = set()
    banned = {}
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
            if user.get("isLocked") is True and permanent.bans:
                profile = UUID(row["uuid"])
                ban = permanent.bans.get(profile)
                if ban is not None and ban.account == UUID(user["uuid"]):
                    banned[str(profile)] = name
                    continue
            names.add(name)
    return names, banned


def _roster(config, online):
    names, banned = _project_members(config)
    current = {name for uid, name in (online or {}).items() if uid not in banned}
    names.update(current)
    if not names:
        return "В списке пока нет игроков."
    ordered = sorted(names, key=str.casefold)
    if online is None:
        return "\n".join(["Не удалось проверить, кто в игре.", "", *ordered])
    return "\n".join(
        f"{name:<16}  {'В игре' if name in current else 'Не в игре'}"
        for name in ordered
    )


def _view(config, action, server):
    if action == "backup-status":
        from omk.owner.hourly_backups import overview  # noqa: PLC0415

        return overview(config, server)
    if action == "player-names" and config.auth_origin is not None:
        names, banned = _project_members(config)
        return _nickname_list(names.union(banned.values()))
    if action == "permanent-bans":
        _, banned = _project_members(config)
        return (
            "\n".join(sorted(banned.values(), key=str.casefold))
            or "Бессрочных банов нет."
        )
    from omk.labs.recovery.recovery_console import (  # noqa: PLC0415
        command,
        online_players,
    )
    from omk.owner.admin_maintenance import credential  # noqa: PLC0415

    try:
        endpoint, password = credential(config, server)
        online = online_players(command(endpoint, password, COMMANDS["players"]))
    except ValueError, RuntimeError, OSError, KeyError:
        online = None
    if action == "player-names":
        if online is None:
            raise ValueError("Player list unavailable")
        return _nickname_list(set(online.values()))
    return _roster(config, online)


def _nickname_list(names: set[str]) -> str:
    if len(names) > MAX_PLAYER_NAMES:
        raise ValueError("Too many player names")
    return "\n".join(sorted(names, key=lambda name: (name.casefold(), name)))


def run(path, server, action, *, confirmed=False):
    """Return fixed private owner console output or a project account view."""
    effect = "none"
    try:
        config = load_operator_config(path)
        if server not in config.servers or (
            action not in COMMANDS and action not in VIEWS
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
        invitations = None
        if action == "invites":
            invitations = [
                InvitationEntry(reference=reference, code=code, date=date)
                for reference, code, date in invitation_summary(config)
            ]
            if len({row.reference for row in invitations}) != len(invitations):
                raise ValueError("Ambiguous invitation inventory")
            output = ""
        elif action in VIEWS:
            output = _view(config, action, server)
        else:
            output = command(endpoint, password, COMMANDS[action])
        if (action != "player-names" and len(output) > 8192) or (
            action not in VIEWS and password in output
        ):
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
            invitations=invitations,
        ).model_dump(mode="json")
    except Exception:
        return ConsoleResult(
            server_id=server,
            command=action,
            ok=False,
            effect=effect,
            error="console_unavailable",
        ).model_dump(mode="json")
