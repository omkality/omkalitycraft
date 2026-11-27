"""Read an owner-only server journal with strict bounds and loss reporting."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from omk.owner.admin import AdminError, _require_private
from omk.owner.owner_access import require_private
from omk.shared.fs import regular

_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})"
)
_SEGMENT_BYTES = 1024**2
_ARCHIVE_BYTES = 256 * _SEGMENT_BYTES
_RECORD_BYTES = 8192


def parse_time(value):
    if not _TIMESTAMP.fullmatch(value):
        raise AdminError("Use an ISO 8601 timestamp with an explicit timezone")
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError, OverflowError:
        raise AdminError("Invalid private journal timestamp") from None


def _string(value, limit):
    return isinstance(value, str) and len(value) <= limit


def _integer(value, minimum, maximum=2**63 - 1):
    return type(value) is int and minimum <= value <= maximum


def _read_row(line, boot, server, kind, validate):
    row = json.loads(line.decode("utf-8"))
    if (
        not isinstance(row, dict)
        or type(row.get("schema")) is not int
        or row["schema"] != 1
        or row.get("boot") != boot
        or row.get("server") != server
        or not _string(row.get("profile"), 80)
        or not _integer(row.get("at_ms"), 1, 9_999_999_999_999)
        or not _string(row.get("core_version"), 40)
    ):
        raise ValueError("Invalid journal record header")
    if row.get("kind") in {"start", "checkpoint", "stop"}:
        if not (
            _integer(row.get("dropped"), 0)
            and _integer(row.get("retention_days"), 1, 90)
            and _integer(row.get("budget_bytes"), _SEGMENT_BYTES, _ARCHIVE_BYTES)
        ):
            raise ValueError("Invalid journal checkpoint")
        return row
    if row.get("kind") != kind or not _integer(row.get("sequence"), 1):
        raise ValueError("Invalid journal record kind or sequence")
    validate(row)
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
        if row["kind"] not in ("start", "checkpoint", "stop"):
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


def _coverage(boots, start, end, incomplete):
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


class JournalScan:
    """Read one bounded, private stream and track coverage independent of filters."""

    def __init__(self, directory, prefix, kind, server, validate):
        self.directory = directory
        self.prefix = prefix
        self.kind = kind
        self.server = server
        self.validate = validate
        self.boots = {}
        self.incomplete = 0

    def _files(self):
        paths = []
        pattern = re.compile(
            rf"{self.prefix}-[0-9]{{13}}-([0-9a-f]{{32}})-[0-9]{{9}}\.jsonl"
        )
        for path in self.directory.glob(self.prefix + "-*.jsonl"):
            match = pattern.fullmatch(path.name)
            if not match or len(paths) >= 512:
                raise AdminError("Unexpected private journal segment layout")
            paths.append((path, match[1]))
        return sorted(paths)

    def _read_segment(self, path, left):
        if not regular(path, self.directory) or path.stat().st_nlink != 1:
            raise OSError("Invalid private journal file")
        require_private(path, secret=True)
        with path.open("rb") as stream:
            data = stream.read(_SEGMENT_BYTES + 1)
        if len(data) > min(left, _SEGMENT_BYTES):
            raise AdminError("Private journal exceeds its scan limit")
        return data

    def records(self, start, end):
        if self.directory.exists():
            _require_private(self.directory, directory=True)
        remaining = _ARCHIVE_BYTES
        for path, ident in self._files():
            try:
                data = self._read_segment(path, remaining)
            except OSError:
                self.incomplete += 1
                continue
            remaining -= len(data)
            *lines, tail = data.split(b"\n")
            damaged = bool(tail) or not data
            boot = self.boots.setdefault(ident, _Boot())
            for line in lines:
                try:
                    if len(line) >= _RECORD_BYTES:
                        raise ValueError("Oversized private journal record")
                    row = _read_row(line, ident, self.server, self.kind, self.validate)
                except ValueError, TypeError, RecursionError:
                    damaged = True
                    continue
                boot.observe(row)
                if row["kind"] == self.kind and start <= row["at_ms"] < end:
                    yield row
            self.incomplete += damaged

    def coverage(self, start, end):
        return _coverage(self.boots, start, end, self.incomplete)
