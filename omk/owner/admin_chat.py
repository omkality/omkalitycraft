"""Read the private, size-bounded Forge chat history through the owner CLI."""

import json
import re
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from omk.owner.admin import (
    AdminError,
    _private_path,
    _require_private,
    _write_private_text,
)
from omk.owner.owner_access import require_private
from omk.shared.fs import regular

_CHANNELS = ("public", "private", "emote", "broadcast", "tellraw")
_SEGMENT = re.compile(r"chat-[0-9]{13}-([0-9a-f]{32})-[0-9]{9}\.jsonl")
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?(?:Z|[+-]\d{2}:\d{2})"
)
_FORMATTING = re.compile(r"§[0-9A-FK-ORa-fk-or]")
_SEGMENT_BYTES = 1024**2
_ARCHIVE_BYTES = 256 * _SEGMENT_BYTES
_RECORD_BYTES = 8192


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


def _time(value):
    if not _TIMESTAMP.fullmatch(value):
        raise AdminError("Use an ISO 8601 timestamp with an explicit timezone")
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError, OverflowError:
        raise AdminError("Invalid chat history timestamp") from None


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


def _string(value, limit):
    return isinstance(value, str) and len(value) <= limit


def _integer(value, minimum, maximum=2**63 - 1):
    return type(value) is int and minimum <= value <= maximum


def _read_row(line, boot, server):
    row = json.loads(line.decode("utf-8"))
    if (
        not isinstance(row, dict)
        or row.get("schema") != 1
        or row.get("boot") != boot
        or row.get("server") != server
        or not _string(row.get("profile"), 80)
        or not _integer(row.get("at_ms"), 1, 9_999_999_999_999)
        or not _string(row.get("core_version"), 40)
    ):
        raise ValueError("Invalid chat record header")
    if row.get("kind") in {"start", "checkpoint", "stop"}:
        if not (
            _integer(row.get("dropped"), 0)
            and _integer(row.get("retention_days"), 1, 90)
            and _integer(row.get("budget_bytes"), _SEGMENT_BYTES, _ARCHIVE_BYTES)
        ):
            raise ValueError("Invalid journal checkpoint")
        return row
    target, recipient = row.get("target"), row.get("recipient")
    if not (
        row.get("kind") == "message"
        and _integer(row.get("sequence"), 1)
        and row.get("channel") in _CHANNELS
        and row.get("outcome") in ("accepted", "sent", "rejected")
        and _valid_identity(row.get("actor"))
        and (recipient is None or _valid_identity(recipient))
        and (target is None or _string(target, 128))
        and _string(row.get("text"), 768)
        and type(row.get("truncated")) is bool
    ):
        raise ValueError("Invalid chat message")
    return row


@dataclass
class _Boot:
    start_ms: int | None = None
    stop_ms: int | None = None
    latest_ms: int = 0
    first_ms: int | None = None
    sequence: int | None = None
    gaps: int = 0
    lost: int = 0

    def observe(self, row):
        now = row["at_ms"]
        self.first_ms = now if self.first_ms is None else min(self.first_ms, now)
        self.latest_ms = max(self.latest_ms, now)
        if row["kind"] == "message":
            sequence = row["sequence"]
            previous = (
                self.sequence
                if self.sequence is not None
                else (0 if self.start_ms else sequence - 1)
            )
            if sequence > previous:
                self.gaps += sequence - previous - 1
                self.sequence = sequence
            return
        self.lost = max(self.lost, row["dropped"])
        if row["kind"] == "start":
            self.start_ms = now
        elif row["kind"] == "stop":
            self.stop_ms = now


def _files(directory):
    paths = []
    for path in directory.glob("chat-*.jsonl"):
        match = _SEGMENT.fullmatch(path.name)
        if not match or len(paths) >= 512:
            raise AdminError("Unexpected chat history segment layout")
        paths.append((path, match[1]))
    return sorted(paths)


def _read_segment(path, directory, remaining):
    if not regular(path, directory) or path.stat().st_nlink != 1:
        raise OSError("Invalid chat history file")
    require_private(path, secret=True)
    with path.open("rb") as stream:
        data = stream.read(_SEGMENT_BYTES + 1)
    if len(data) > min(remaining, _SEGMENT_BYTES):
        raise AdminError("Chat history exceeds its scan limit")
    return data


def _coverage(boots, start, end, incomplete, truncated):
    intervals = sorted(
        (boot.first_ms, boot.latest_ms)
        for boot in boots.values()
        if boot.first_ms is not None
    )
    through = start
    uncovered = []
    for first, last in intervals:
        if last < through or first >= end:
            continue
        if first > through:
            uncovered.append([through, first])
        through = min(max(through, last), end)
    if through < end:
        uncovered.append([through, end])
    within = {
        ident: boot
        for ident, boot in boots.items()
        if boot.first_ms is not None and boot.first_ms < end and boot.latest_ms >= start
    }
    latest_boot = max(boots, key=lambda key: boots[key].latest_ms, default=None)
    return {
        "requested_ms": [start, end],
        "uncovered_ms": uncovered,
        "incomplete_segments": incomplete,
        "truncated_messages": truncated,
        "observed_sequence_gaps": sum(boot.gaps for boot in within.values()),
        "reported_dropped": sum(boot.lost for boot in within.values()),
        "latest_boot_open": latest_boot in within
        and boots[latest_boot].stop_ms is None,
        "unclean_previous_boots": [
            ident
            for ident, boot in within.items()
            if ident != latest_boot and boot.stop_ms is None
        ],
    }


def _scan(directory, args, start, end, player, recipient):
    history = deque(maxlen=args.context)
    result = {}
    boots = {}
    remaining = _ARCHIVE_BYTES
    index = incomplete = matches = after = truncated = 0
    limited = False
    for path, ident in _files(directory):
        try:
            data = _read_segment(path, directory, remaining)
        except OSError:
            incomplete += 1
            continue
        remaining -= len(data)
        *lines, tail = data.split(b"\n")
        damaged = bool(tail) or not data
        boot = boots.setdefault(ident, _Boot())
        for line in lines:
            try:
                if len(line) >= _RECORD_BYTES:
                    raise ValueError("Oversized chat message")
                row = _read_row(line, ident, args.server)
            except ValueError, TypeError, RecursionError:
                damaged = True
                continue
            boot.observe(row)
            if row["kind"] != "message" or not start <= row["at_ms"] < end:
                continue
            truncated += row["truncated"]
            actor, target = row["actor"], row["recipient"]
            selection = (
                (args.channel is None or row["channel"] == args.channel)
                and (
                    player is None
                    or _matches(actor, player)
                    or _matches(target, player)
                )
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
            index += 1
        incomplete += damaged
    return {
        "ok": True,
        "server": args.server,
        "matches": matches,
        "more_matches": limited,
        "coverage": _coverage(boots, start, end, incomplete, truncated),
        "entries": [result[key] for key in sorted(result)],
    }


def run_chat(config, args):
    """Search only the configured server's private journal and optionally save one export."""
    if args.server not in config.servers:
        raise AdminError("Server is outside the owner allowlist")
    start, end = _time(args.since), _time(args.until)
    if not timedelta(0) < end - start <= timedelta(days=90):
        raise AdminError("Choose a chat history interval up to 90 days")
    if not 1 <= args.limit <= 100:
        raise AdminError("Choose between 1 and 100 chat matches")
    player, recipient = _identity_filter(args.player), _identity_filter(args.recipient)
    directory = _private_path(config.private, f"chat-history/{args.server}")
    if directory.exists():
        _require_private(directory, directory=True)
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
