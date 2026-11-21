"""Apply project-owned Drasl account locks and drain bound game connections."""

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from omk.accounts.account_recovery import _operator, _snapshot
from omk.game.project_moderation import (
    HISTORY_LIMIT,
    HistoryEntry,
    Refused,
)
from omk.labs.recovery.recovery_console import RecoveryConsole
from omk.owner.admin import _private_path, _require_private, _write_private_text
from omk.owner.admin_maintenance import credential

USERS = "/drasl/api/v3/users"


class PermanentBan(HistoryEntry):
    """Bind a project-owned Drasl lock to its exact account and game profile."""

    kind: Literal["ban"] = "ban"
    expires: Literal[None] = None
    account: UUID
    player: str = Field(pattern=r"^[A-Za-z0-9_]{1,16}$")
    stage: Literal["locking", "active", "unlocking"] = "locking"


class PermanentHistory(BaseModel):
    """Keep lock ownership and its history in one private atomic record."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    bans: dict[UUID, PermanentBan] = Field(default_factory=dict, max_length=1024)
    entries: list[HistoryEntry] = Field(default_factory=list, max_length=HISTORY_LIMIT)


def load(root: Path) -> tuple[Path, PermanentHistory]:
    """Read the bounded private project lock journal."""
    path = _private_path(root, "project-permanent-bans.json")
    if not path.exists():
        return path, PermanentHistory()
    _require_private(path, secret=True)
    limit = 2 * 1024**2
    with path.open("rb") as file:
        raw = file.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Project ban store exceeds its size limit")
    history = PermanentHistory.model_validate_json(raw)
    if any(key != ban.uuid for key, ban in history.bans.items()):
        raise ValueError("Project ban store contains an unrelated identity")
    return path, history


def _identify(user):
    try:
        snapshot = _snapshot(user)
        locked = user["isLocked"]
    except AttributeError, KeyError, TypeError:
        raise ValueError("Invalid Drasl account identity") from None
    if type(locked) is not bool:
        raise ValueError("Invalid Drasl lock state")
    if len(snapshot["players"]) != 1:
        raise Refused("ambiguous")
    profile = snapshot["players"][0]
    return UUID(snapshot["account"]), UUID(profile["uuid"]), profile["name"], locked


def _lookup(client, token, player):
    users = client.request("GET", USERS, token=token)
    if not isinstance(users, list) or len(users) > 1000:
        raise ValueError("Invalid Drasl account inventory")
    matching = []
    for user in users:
        profiles = user.get("players") if isinstance(user, dict) else None
        if not isinstance(profiles, list) or any(
            not isinstance(p, dict) for p in profiles
        ):
            raise ValueError("Invalid Drasl profile inventory")
        if any(
            str(p.get("name", "")).casefold() == player.casefold() for p in profiles
        ):
            matching.append(user)
    if not matching:
        raise Refused("profile_not_found")
    if len(matching) != 1:
        raise Refused("ambiguous")
    return _identify(matching[0])


def _locked(client, token, ban):
    value = client.request("GET", f"{USERS}/{ban.account}", token=token)
    account, profile, player, locked = _identify(value)
    if (account, profile, player) != (ban.account, ban.uuid, ban.player):
        raise Refused("ambiguous")
    return locked


def _save(config, path, history, event=None):
    if event is not None:
        history.entries = [*history.entries[-(HISTORY_LIMIT - 1) :], event]
    _write_private_text(path, config.private, history.model_dump_json())


def _disconnect(config, ban):
    def drain(server):
        try:
            endpoint, password = credential(config, server)
            RecoveryConsole(endpoint, password).disconnect({str(ban.uuid): ban.player})
            return None
        except KeyError, OSError, RuntimeError, ValueError:
            return server

    if not config.servers:
        return []
    with ThreadPoolExecutor(max_workers=min(16, len(config.servers))) as workers:
        return [
            server for server in workers.map(drain, sorted(config.servers)) if server
        ]


def _ban(
    config, result, history, path, ban, discard_temporary, reason, client, token, caller
):
    if ban is None:
        account, profile, name, locked = _lookup(client, token, result.player)
        if str(account) == caller:
            raise Refused("operator_account")
        if locked:
            raise Refused("account_locked")
        now = int(time.time())
        if len(history.bans) == 1024:
            raise ValueError("Project ban store is full")
        ban = PermanentBan(
            account=account, uuid=profile, player=name, time=now, reason=reason
        )
        if _locked(client, token, ban):
            raise Refused("account_locked")
        history.bans[profile] = ban
        _save(config, path, history)
    if str(ban.account) == caller:
        raise Refused("operator_account")
    if ban.stage == "unlocking":
        raise Refused("account_locked")
    locked = _locked(client, token, ban)
    if ban.stage == "locking":
        result.effect = "unknown"
        client.request(
            "PATCH",
            f"{USERS}/{ban.account}",
            {"isLocked": True, "resetApiToken": True, "resetMinecraftToken": True},
            token,
        )
        if not _locked(client, token, ban):
            raise ValueError("Drasl lock was not confirmed")
        ban.stage = "active"
        event = HistoryEntry(
            uuid=ban.uuid, kind="ban", time=ban.time, reason=ban.reason
        )
        _save(config, path, history, event)
    elif not locked:
        raise Refused("account_locked")
    discard_temporary(ban.uuid)
    result.unreachable.extend(_disconnect(config, ban))


def _unban(
    config, result, history, path, ban, discard_temporary, client, token, caller
):
    if str(ban.account) == caller:
        raise Refused("operator_account")
    locked = _locked(client, token, ban)
    discard_temporary(ban.uuid)
    if ban.stage != "unlocking" and (locked or ban.stage == "active"):
        ban.stage = "unlocking"
        _save(config, path, history)
    if locked:
        result.effect = "unknown"
        client.request("PATCH", f"{USERS}/{ban.account}", {"isLocked": False}, token)
        if _locked(client, token, ban):
            raise ValueError("Drasl unlock was not confirmed")
    event = (
        HistoryEntry(uuid=ban.uuid, kind="unban", time=int(time.time()))
        if ban.stage == "unlocking"
        else None
    )
    del history.bans[ban.uuid]
    _save(config, path, history, event)


def update(config, result, history, path, discard_temporary, reason, profile=None):
    """Apply or remove a lock while holding the moderation and recovery locks."""
    matching = [
        ban
        for ban in history.bans.values()
        if ban.player.casefold() == result.player.casefold()
        and (profile is None or str(ban.uuid) == profile)
    ]
    if len(matching) > 1:
        raise Refused("ambiguous")
    ban = next(iter(matching), None)
    client, token, caller = _operator(config)
    if result.command == "unban":
        if ban is None:
            raise Refused("not_banned")
        _unban(
            config, result, history, path, ban, discard_temporary, client, token, caller
        )
    else:
        _ban(
            config,
            result,
            history,
            path,
            ban,
            discard_temporary,
            reason,
            client,
            token,
            caller,
        )
