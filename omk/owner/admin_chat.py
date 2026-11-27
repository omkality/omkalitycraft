"""Read the private, size-bounded Forge chat history through the owner CLI."""

import json
import re
from collections import deque
from datetime import timedelta
from uuid import UUID

from omk.owner.admin import (
    AdminError,
    _private_path,
    _write_private_text,
)
from omk.owner.private_journal import JournalScan, _string, parse_time

_CHANNELS = ("public", "private", "emote", "broadcast", "tellraw")
_FORMATTING = re.compile(r"§[0-9A-FK-ORa-fk-or]")


def add_chat_parser(actions):
    """Register an owner-only search with an explicit time window."""
    parser = actions.add_parser(
        "chat-history", help="Search the private server chat journal"
    )
    parser.add_argument("--server", required=True)
    parser.add_argument("--from", dest="since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--player", help="Account UUID or historical player nickname")
    parser.add_argument("--recipient", help="Recipient UUID or nickname")
    parser.add_argument("--channel", choices=_CHANNELS)
    parser.add_argument("--context", type=int, choices=range(4), default=0)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--export", action="store_true")


def _identity_filter(value):
    if value is None:
        return None
    if not 1 <= len(value) <= 128 or not value.isprintable():
        raise AdminError("Use an account UUID or a player nickname")
    try:
        return str(UUID(value))
    except ValueError:
        return value.casefold()


def _matches(identity, key):
    return identity is not None and key in (
        identity["uuid"],
        identity["name"].casefold(),
        _FORMATTING.sub("", identity["display"]).casefold(),
        _FORMATTING.sub("", identity["nickname"] or "").casefold(),
    )


def _valid_identity(value):
    if not isinstance(value, dict) or set(value) != {
        "kind",
        "uuid",
        "name",
        "display",
        "nickname",
    }:
        return False
    kind, uuid, name, display = (
        value[key] for key in ("kind", "uuid", "name", "display")
    )
    if not (
        _string(name, 32)
        and _string(display, 128)
        and (value["nickname"] is None or _string(value["nickname"], 128))
    ):
        return False
    if kind == "console":
        return uuid is None
    try:
        return kind == "player" and isinstance(uuid, str) and str(UUID(uuid)) == uuid
    except ValueError:
        return False


def _validate_message(row):
    target, recipient = row.get("target"), row.get("recipient")
    if not (
        row.get("channel") in _CHANNELS
        and row.get("outcome") in ("accepted", "sent", "rejected")
        and _valid_identity(row.get("actor"))
        and (recipient is None or _valid_identity(recipient))
        and (target is None or _string(target, 128))
        and _string(row.get("text"), 768)
        and type(row.get("truncated")) is bool
    ):
        raise ValueError("Invalid chat message")


def _scan(directory, args, start, end, player, recipient):
    history = deque(maxlen=args.context)
    result = {}
    scan = JournalScan(directory, "chat", "message", args.server, _validate_message)
    matches = after = truncated = 0
    limited = False
    for index, row in enumerate(scan.records(start, end)):
        truncated += row["truncated"]
        actor, target = row["actor"], row["recipient"]
        selection = (
            (args.channel is None or row["channel"] == args.channel)
            and (player is None or _matches(actor, player) or _matches(target, player))
            and (
                recipient is None
                or _matches(target, recipient)
                or recipient == (row["target"] or "").casefold()
            )
        )
        if selection and matches < args.limit:
            for offset, neighbor in history:
                result.setdefault(offset, {"match": False, "message": neighbor})
            result[index] = {"match": True, "message": row}
            matches += 1
            after = args.context
        else:
            limited |= selection
            if after > 0:
                result[index] = {"match": False, "message": row}
                after -= 1
        history.append((index, row))
    return {
        "ok": True,
        "server": args.server,
        "matches": matches,
        "more_matches": limited,
        "coverage": {**scan.coverage(start, end), "truncated_messages": truncated},
        "entries": [result[key] for key in sorted(result)],
    }


def run_chat(config, args):
    """Search only the configured server's private journal and optionally save one export."""
    if args.server not in config.servers:
        raise AdminError("Server is outside the owner allowlist")
    start, end = parse_time(args.since), parse_time(args.until)
    if not timedelta(0) < end - start <= timedelta(days=90):
        raise AdminError("Choose a chat history interval up to 90 days")
    if not 1 <= args.limit <= 100:
        raise AdminError("Choose between 1 and 100 chat matches")
    player, recipient = _identity_filter(args.player), _identity_filter(args.recipient)
    directory = _private_path(config.private, f"chat-history/{args.server}")
    result = _scan(
        directory,
        args,
        round(start.timestamp() * 1000),
        round(end.timestamp() * 1000),
        player,
        recipient,
    )
    if args.export:
        export = config.private / "chat-export.json"
        _write_private_text(
            export, config.private, json.dumps(result, ensure_ascii=False) + "\n"
        )
        result["export"] = str(export)
    return result
