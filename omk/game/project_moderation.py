"""Owner-written restrictions read by every game server in a project."""

import os
import re
import time
import unicodedata
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import astuple, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from omk.accounts.account_recovery import _locked as account_lock
from omk.labs.recovery.recovery_console import ConsoleError, command, online_players
from omk.owner.admin import (
    _client,
    _private_path,
    _require_private,
    _write_private_text,
    load_operator_config,
    revoke_invite_reference,
)
from omk.owner.admin_maintenance import credential
from omk.owner.panels.owner_moderation import duration_seconds

DIRECTORY = "project-moderation"
STATE = "restrictions.tsv"
HISTORY = "moderation-history.json"
HISTORY_LIMIT = 1024
RECENT_LIMIT = 12
HEADER = "omk-project-moderation-v1"
MAX_BYTES = 65536
MAX_SECONDS = 31536000
NAME = re.compile(r"[A-Za-z0-9_]{1,16}")
TIMESTAMP = re.compile(r"[1-9][0-9]{0,11}")


@dataclass(frozen=True)
class Restriction:
    """Represent a project-wide moderation entry bound to a player UUID."""

    kind: str
    uuid: str
    player: str
    created: int
    expires: int | None
    reason: str


class HistoryEntry(BaseModel):
    """Record an applied change to one player's project restrictions."""

    model_config = ConfigDict(extra="forbid", strict=True)
    uuid: UUID
    kind: Literal["ban", "mute", "unban"]
    time: int = Field(gt=0, le=253402300799)
    expires: int | None = Field(default=None, gt=0, le=253402300799)
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def safe_reason(cls, value: str) -> str:
        """Reject control sequences and oversized history reasons."""
        if value and not _valid_reason(value):
            raise ValueError("Invalid moderation reason")
        return value


class PendingEntry(BaseModel):
    """Expose the staged event only when its corresponding restrictions are installed."""

    model_config = ConfigDict(extra="forbid", strict=True)
    restrictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event: HistoryEntry


class History(BaseModel):
    """Bounded owner-only journal outside the directory mounted by Minecraft."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    entries: list[HistoryEntry] = Field(default_factory=list, max_length=HISTORY_LIMIT)
    pending: PendingEntry | None = None


class Result(BaseModel):
    """Describe the outcome of a moderation lookup or update."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    action: Literal["owner.project-moderation"] = "owner.project-moderation"
    command: Literal["init", "ban", "mute", "unban", "revoke-invite"]
    player: str = Field(max_length=16)
    ok: bool = False
    effect: Literal["none", "applied", "unknown"] = "none"
    expires_at: int | None = None
    error: (
        Literal[
            "invalid_request",
            "unavailable",
            "player_offline",
            "ambiguous",
            "not_banned",
            "already_banned",
            "inconsistent_servers",
            "profile_not_found",
            "account_locked",
            "operator_account",
        ]
        | None
    ) = None
    unreachable: list[str] = Field(default_factory=list, max_length=100)


class Refused(ValueError):
    """Report a moderation operation rejected by the current policy or state."""

    pass


def _uuid(value):
    if str(UUID(value)) != value:
        raise ValueError("Noncanonical UUID")
    return value


def _valid_reason(reason):
    return 1 <= len(reason) <= 128 and all(
        not unicodedata.category(c).startswith("C") and c != "§" for c in reason
    )


def _read(root):
    path = _private_path(root, f"{DIRECTORY}/{STATE}")
    _require_private(path, secret=True)
    with path.open("rb") as file:
        data = file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or not data.endswith(b"\n"):
        raise ValueError("Invalid moderation file size or terminator")
    header, *lines = data.decode("utf-8")[:-1].split("\n")
    marker, store = header.split("\t")
    if marker != HEADER:
        raise ValueError("Unknown moderation file format")
    entries = {}
    for line in lines:
        kind, uid, name, created, expires, reason = line.split("\t")
        key = (kind, _uuid(uid))
        if (
            kind not in {"ban", "mute"}
            or key in entries
            or not NAME.fullmatch(name)
            or not TIMESTAMP.fullmatch(created)
            or not TIMESTAMP.fullmatch(expires)
            or not 0 < int(expires) - int(created) <= MAX_SECONDS
            or not _valid_reason(reason)
        ):
            raise ValueError("Invalid moderation record")
        entries[key] = Restriction(kind, uid, name, int(created), int(expires), reason)
    return _uuid(store), entries


@contextmanager
def _lock(root) -> Generator[None]:
    path = _private_path(root, "project-moderation.lock")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(b"0")
    except FileExistsError:
        pass
    _require_private(path, secret=True)
    with path.open("r+b") as file:
        if os.name == "nt":
            import msvcrt  # noqa: PLC0415

            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # noqa: PLC0415

            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def _snapshot(store, entries):
    lines = [f"{HEADER}\t{store}"]
    lines.extend(
        "\t".join(map(str, astuple(entry))) for _, entry in sorted(entries.items())
    )
    value = "\n".join(lines) + "\n"
    if len(value.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Project moderation file is full")
    return value


def _history(path: Path, snapshot: str) -> History:
    if not path.exists():
        return History()
    _require_private(path, secret=True)
    limit = 1024**2
    with path.open("rb") as file:
        raw = file.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Moderation history exceeds its size limit")
    history = History.model_validate_json(raw)
    if (
        history.pending is not None
        and history.pending.restrictions_sha256 == sha256(snapshot.encode()).hexdigest()
    ):
        history.entries = [*history.entries, history.pending.event][-HISTORY_LIMIT:]
    history.pending = None
    return history


def player_moderation(
    root: Path, uid: str
) -> tuple[list[Restriction], list[HistoryEntry]]:
    """Read active restrictions and recent applied events for an authenticated UUID."""
    from omk.game.project_permanent_bans import load  # noqa: PLC0415

    profile = UUID(uid)
    with _lock(root):
        store, entries = _read(root)
        history_path = _private_path(root, HISTORY)
        history = _history(history_path, _snapshot(store, entries))
        _, permanent = load(root)
    now = int(time.time())
    active = [
        entry
        for entry in entries.values()
        if entry.uuid == uid and entry.expires is not None and entry.expires > now
    ]
    if ban := permanent.bans.get(profile):
        if ban.stage != "active":
            raise Refused("unavailable")
        active.append(Restriction("ban", uid, ban.player, ban.time, None, ban.reason))
    recent = sorted(
        (
            entry
            for entry in reversed(history.entries + permanent.entries)
            if entry.uuid == profile
        ),
        key=lambda event: event.time,
        reverse=True,
    )[:RECENT_LIMIT]
    return active, recent


def initialize(root):
    """Create the shared store once. Validate and keep any existing restrictions."""
    _require_private(root, directory=True)
    with _lock(root):
        path = _private_path(root, f"{DIRECTORY}/{STATE}")
        if path.exists():
            return _read(root)[0], False
        store = str(uuid4())
        _write_private_text(path, root, _snapshot(store, {}), newline="\n")
        return store, True


def _find_player(config, store, player, result):
    registered = None
    if config.auth_origin is not None:
        registered = _client(config).game_profile(player)
        if registered is None:
            raise Refused("profile_not_found")
    endpoints = {
        server: credential(config, server) for server in sorted(config.servers)
    }
    if not endpoints:
        raise Refused("invalid_request")

    def inspect(item):
        server, (endpoint, password) = item
        try:
            proof = command(endpoint, password, "list omk-moderation project")
            if proof.strip() != f"OMK_PROJECT_MODERATION_V1 {store}":
                raise Refused("inconsistent_servers")
            return server, online_players(command(endpoint, password, "list uuids"))
        except OSError, ConsoleError:
            return server, None

    matches = {}
    with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
        for server, online in pool.map(inspect, endpoints.items()):
            if online is None:
                result.unreachable.append(server)
            else:
                matches.update(
                    (uid, name)
                    for uid, name in online.items()
                    if name.lower() == player.lower()
                )
    if registered is not None:
        if matches.keys() - {registered[0]}:
            raise Refused("inconsistent_servers")
        return registered
    if len(matches) != 1:
        raise Refused("ambiguous" if matches else "player_offline")
    return next(iter(matches.items()))


def _update(config, result, seconds, reason):
    from omk.game.project_permanent_bans import load, update  # noqa: PLC0415

    action, player = result.command, result.player
    store, entries = _read(config.private)
    history_path = _private_path(config.private, HISTORY)
    permanent_path, permanent = load(config.private)
    if (action == "ban" and seconds is None) or (
        action == "unban"
        and any(
            b.player.casefold() == player.casefold() for b in permanent.bans.values()
        )
    ):
        with account_lock(config):
            update(config, result, permanent, permanent_path, entries, reason)
        return
    if action != "unban":
        uid, name = _find_player(config, store, player, result)
        if action == "ban" and UUID(uid) in permanent.bans:
            raise Refused("already_banned")
    now = int(time.time())
    active = {
        key: entry
        for key, entry in entries.items()
        if entry.expires is not None and entry.expires > now
    }
    if action == "unban":
        keys = [
            key
            for key, entry in active.items()
            if entry.kind == "ban" and entry.player.lower() == player.lower()
        ]
        if len(keys) != 1:
            raise Refused("ambiguous" if keys else "not_banned")
        _, uid = keys[0]
        del active[keys[0]]
        expires = None
    else:
        key = (action, uid)
        previous = active.get(key)
        if previous and action == "ban":
            raise Refused("already_banned")
        if previous and previous.expires >= now + seconds:
            result.expires_at = previous.expires
            return
        active[key] = Restriction(action, uid, name, now, now + seconds, reason)
        expires = active[key].expires
    value = _snapshot(store, active)
    path = _private_path(config.private, f"{DIRECTORY}/{STATE}")
    history = _history(history_path, _snapshot(store, entries))
    history.entries = history.entries[-(HISTORY_LIMIT - 1) :]
    history.pending = PendingEntry(
        restrictions_sha256=sha256(value.encode()).hexdigest(),
        event=HistoryEntry(
            uuid=UUID(uid),
            kind=action,
            time=now,
            expires=expires,
            reason=reason if action != "unban" else "",
        ),
    )
    # Stage the event before replacing the live file. Its hash distinguishes a
    # completed update from a failed or interrupted write across process restarts.
    _write_private_text(history_path, config.private, history.model_dump_json())
    result.effect = "unknown"
    _write_private_text(path, config.private, value, newline="\n")
    result.expires_at = expires


def run(path, action, player, *, duration="", reason="", confirmed=False):
    """Apply a project-wide restriction or revoke an unused invitation."""
    result = Result(command=action, player=player[:16])
    try:
        config = load_operator_config(path)
        if action == "init":
            if player or duration or reason or confirmed:
                raise Refused("invalid_request")
            _, created = initialize(config.private)
            result.effect = "applied" if created else "none"
        elif action == "revoke-invite":
            if (
                not confirmed
                or duration
                or reason
                or not re.fullmatch(r"[a-f0-9]{12}", player)
            ):
                raise Refused("invalid_request")
            result.effect = "unknown"
            changed = revoke_invite_reference(config, player)
            result.effect = "applied" if changed else "none"
        else:
            reason = reason or "Owner moderation"
            if (
                not NAME.fullmatch(player)
                or not _valid_reason(reason)
                or (action == "ban" and not confirmed)
                or (action == "unban" and duration)
            ):
                raise Refused("invalid_request")
            try:
                if action == "ban" and duration == "perm":
                    seconds = None
                else:
                    seconds = 0 if action == "unban" else duration_seconds(duration)
            except ValueError:
                raise Refused("invalid_request") from None
            with _lock(config.private):
                _update(config, result, seconds, reason)
            result.effect = "applied"
        result.ok = True
    except Refused as error:
        result.error = str(error)
    except OSError, RuntimeError, ValueError:
        result.error = "unavailable"
    return result.model_dump(mode="json")
