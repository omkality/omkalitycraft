"""Owner-only, single-shot moderation of players through Core 1.12.2."""

import base64
import json
import re
import unicodedata
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from omk.owner.admin import load_operator_config
from omk.owner.owner_result import ServerId


def duration_seconds(value):
    match = re.fullmatch(r"([1-9][0-9]{0,7})([smhdw])", value)
    if not match:
        raise ValueError("Use a positive duration such as 10m, 20h or 1d")
    seconds = (
        int(match[1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[match[2]]
    )
    if seconds > 31536000:
        raise ValueError("Maximum duration is 365d")
    return seconds


class ModerationResult(BaseModel):
    """Report an owner moderation action and its observed outcome."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    action: Literal["owner.moderation"] = "owner.moderation"
    server_id: ServerId
    command: Literal["kick", "ban", "mute", "unban"]
    player: str = Field(max_length=16)
    ok: bool
    effect: Literal["none", "applied", "unknown"]
    expires_at: int | None = None
    error: (
        Literal[
            "invalid_request",
            "player_offline",
            "unavailable",
            "already_banned",
            "refused",
            "not_banned",
            "changed",
        ]
        | None
    ) = None


class BanLookup(BaseModel):
    """Describe a recorded ban and the identity used to confirm its removal."""

    model_config = ConfigDict(extra="forbid", strict=True)
    nonce: str = Field(pattern=r"^[a-f0-9]{32}$")
    player: str = Field(pattern=r"^[A-Za-z0-9_]{1,16}$")
    uuid: str | None
    token: str | None
    error: Literal["not_banned", "refused"] | None


def _banned_target(command, endpoint, password, player, nonce):
    output = command(
        endpoint, password, f"list omk-moderation lookup-ban {nonce} {player}"
    )
    prefix = "OMK_BAN_LOOKUP_V1 "
    if len(output) > 4096 or not output.startswith(prefix):
        raise ValueError("Unsupported ban lookup")
    value = BanLookup.model_validate_json(output[len(prefix) :])
    if value.nonce != nonce or value.player.lower() != player.lower():
        raise ValueError("Unrelated ban lookup")
    if value.error == "not_banned" and value.uuid is None and value.token is None:
        return None
    if value.error is not None or not value.uuid or not value.token:
        raise ValueError("Ban lookup refused")
    if str(UUID(value.uuid)) != value.uuid or not re.fullmatch(
        r"[a-f0-9]{64}", value.token
    ):
        raise ValueError("Invalid ban identity")
    return value.uuid, value.player, value.token


def _receipt(output, result, nonce, uid, action):
    prefix = "OMK_MODERATION_V1 "
    if len(output) > 4096 or not output.startswith(prefix):
        raise ValueError("Unsupported moderation bridge")
    receipt = json.loads(output[len(prefix) :])
    if set(receipt) != {
        "nonce",
        "uuid",
        "command",
        "ok",
        "effect",
        "expires_at",
        "error",
    }:
        raise ValueError("Invalid receipt")
    if (
        receipt.pop("nonce") != nonce
        or receipt.pop("uuid") != uid
        or receipt.pop("command") != action
    ):
        raise ValueError("Unrelated receipt")
    accepted = ModerationResult(**{**result, **receipt})
    if accepted.ok != (accepted.effect == "applied") or accepted.ok != (
        accepted.error is None
    ):
        raise ValueError("Inconsistent receipt")
    if accepted.ok and ((action in {"kick", "unban"}) != (accepted.expires_at is None)):
        raise ValueError("Invalid expiry")
    return accepted.model_dump(mode="json")


def kick_for_maintenance(config, server, reason):
    """Send the maintenance reason to each player on the selected server."""
    from omk.labs.recovery.recovery_console import (  # noqa: PLC0415
        ConsoleError,
        command,
        online_players,
    )
    from omk.owner.admin_maintenance import credential  # noqa: PLC0415

    endpoint, password = credential(config, server)
    players = online_players(command(endpoint, password, "list uuids"))
    encoded = base64.urlsafe_b64encode(reason.encode("utf-8")).decode().rstrip("=")
    for uid, player in players.items():
        nonce = uuid4().hex
        result = {"server_id": server, "command": "kick", "player": player}
        receipt = _receipt(
            command(
                endpoint,
                password,
                f"list omk-moderation kick {nonce} {uid} {player} 0 {encoded} v1",
            ),
            result,
            nonce,
            uid,
            "kick",
        )
        if not receipt["ok"]:
            remaining = online_players(command(endpoint, password, "list uuids"))
            if uid in remaining:
                raise ConsoleError(
                    "Minecraft refused to disconnect a player for maintenance"
                )


def run(path, server, action, player, *, duration="", reason="", confirmed=False):
    result = {
        "server_id": server,
        "command": action,
        "player": player[:16],
        "ok": False,
        "effect": "none",
    }
    try:
        config = load_operator_config(path)
        if server not in config.servers or action not in {
            "kick",
            "ban",
            "mute",
            "unban",
        }:
            raise ValueError("Invalid server or action")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", player):
            raise ValueError("Invalid player")
        seconds = duration_seconds(duration) if action in {"ban", "mute"} else 0
        if (action in {"kick", "unban"} and duration) or (
            action == "ban" and not confirmed
        ):
            raise ValueError("Ban requires explicit confirmation")
        reason = reason or "Owner moderation"
        if len(reason) > 128 or any(
            unicodedata.category(c).startswith("C") or c == "§" for c in reason
        ):
            raise ValueError("Invalid reason")
        from omk.labs.recovery.recovery_console import (  # noqa: PLC0415
            command,
            online_players,
        )
        from omk.owner.admin_maintenance import credential  # noqa: PLC0415

        endpoint, password = credential(config, server)
    except Exception:
        return ModerationResult(**result, error="invalid_request").model_dump(
            mode="json"
        )
    try:
        nonce = uuid4().hex
        if action == "unban":
            target = _banned_target(command, endpoint, password, player, nonce)
            if target is None:
                return ModerationResult(**result, error="not_banned").model_dump(
                    mode="json"
                )
            uid, name, encoded = target
        else:
            online = online_players(command(endpoint, password, "list uuids"))
            targets = [
                (uid, name)
                for uid, name in online.items()
                if name.lower() == player.lower()
            ]
            if len(targets) != 1:
                return ModerationResult(**result, error="player_offline").model_dump(
                    mode="json"
                )
            uid, name = targets[0]
            uid = str(UUID(str(uid)))
            encoded = (
                base64.urlsafe_b64encode(reason.encode("utf-8"))
                .decode("ascii")
                .rstrip("=")
            )
        text = (
            f"list omk-moderation {action} {nonce} {uid} {name} {seconds} {encoded} v1"
        )
        result["effect"] = (
            "unknown"  # Never resend a mutation after a missing/invalid receipt.
        )
        output = command(endpoint, password, text)
        return _receipt(output, result, nonce, uid, action)
    except Exception:
        return ModerationResult(**result, error="unavailable").model_dump(mode="json")
