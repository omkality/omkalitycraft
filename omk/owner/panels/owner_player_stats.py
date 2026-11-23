"""Read a player's saved time and moderation from the private owner backend."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from omk.game.player_time import saved_playtime
from omk.game.project_moderation import NAME, player_moderation
from omk.labs.recovery.recovery_console import command, online_players
from omk.owner.admin import _client, load_operator_config
from omk.owner.admin_maintenance import credential
from omk.owner.owner_result import ServerId

_OPERATIONS = {"ban": "Бан", "mute": "Мут", "unban": "Разбан", "unmute": "Размут"}
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class Result(BaseModel):
    """Return a read-only player card bound to the requested nickname and server."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    action: Literal["owner.player-stats"] = "owner.player-stats"
    server_id: ServerId
    player: str = Field(max_length=16)
    ok: bool = False
    output: str = Field(default="", max_length=8192)
    error: (
        Literal["invalid_request", "profile_not_found", "profile_unavailable"] | None
    ) = None


def _date(seconds: int) -> str:
    if seconds > 253402300799:
        return "дата недоступна"
    return (_EPOCH + timedelta(seconds=seconds)).strftime("%d.%m.%Y %H:%M UTC")


def _connection(config, server: str, uid: str) -> str:
    try:
        endpoint, password = credential(config, server)
        playing = uid in online_players(command(endpoint, password, "list uuids"))
    except KeyError, OSError, RuntimeError, ValueError:
        return "Статус в игре недоступен"
    return "Сейчас в игре" if playing else "Сейчас не в игре"


def _time(config, server: str, uid: str) -> str:
    try:
        saved = saved_playtime(config, server, uid)
    except OSError, RuntimeError, ValueError:
        return "Активное время · данные недоступны"
    if "active_millis" not in saved:
        return "Активное время появится после игры и сохранения мира"
    seconds = saved["active_millis"] // 1000
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"Активное время · {hours} ч {minutes:02d} мин {seconds:02d} с"


def _moderation(root: Path, uid: str) -> list[str]:
    try:
        active, recent = player_moderation(root, uid)
    except OSError, RuntimeError, ValueError:
        return ["Данные модерации недоступны."]
    lines = [
        "Действующие ограничения на проекте",
        *(
            f"{_OPERATIONS[entry.kind]} до {_date(entry.expires)} · {entry.reason}"
            if entry.expires is not None
            else f"Бессрочный бан · {entry.reason}"
            for entry in active
        ),
    ]
    if not active:
        lines.append("Нет действующих ограничений.")
    lines.extend(["", "Недавние действия на проекте"])
    for entry in recent:
        label = _OPERATIONS[entry.kind]
        if entry.expires is not None:
            label += f" до {_date(entry.expires)} · {entry.reason}"
        elif entry.kind == "ban":
            label = f"Бессрочный бан · {entry.reason}"
        lines.append(f"{_date(entry.time)} · {label}")
    if not recent:
        lines.append("В журнале пока нет записей об этом игроке.")
    return lines


def run(path: Path, server: str, player: str) -> dict:
    """Resolve the current Drasl UUID and read the selected server and project views."""
    result = Result(server_id=server, player=player[:16])
    if not NAME.fullmatch(player):
        result.error = "invalid_request"
        return result.model_dump(mode="json")
    try:
        config = load_operator_config(path)
        if server not in config.servers:
            result.error = "invalid_request"
            return result.model_dump(mode="json")
        profile = _client(config).game_profile(player)
    except OSError, RuntimeError, ValueError:
        result.error = "profile_unavailable"
        return result.model_dump(mode="json")
    if profile is None:
        result.error = "profile_not_found"
        return result.model_dump(mode="json")
    uid, name = profile
    result.output = "\n".join(
        (
            f"Игрок · {name}",
            f"Сервер · {server}",
            _connection(config, server, uid),
            _time(config, server, uid),
            "",
            *_moderation(config.private, uid),
        )
    )
    result.ok = True
    return result.model_dump(mode="json")
