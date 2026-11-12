"""Single-writer, size-bounded SQLite resource history. Contains no player data."""

import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
from pathlib import Path

MIB = 1024 * 1024
METRIC = re.compile(r"[a-z][A-Za-z0-9_.-]{0,159}")


def validate_sample(sample):
    if (
        not isinstance(sample, dict)
        or not {
            "schema",
            "at",
            "collector",
            "sequence",
            "host",
            "config_sha256",
            "releases",
            "host_boot",
            "interval_seconds",
            "metrics",
            "issues",
            "sources",
        }
        <= set(sample)
        or set(sample)
        - {
            "schema",
            "at",
            "collector",
            "sequence",
            "host",
            "config_sha256",
            "releases",
            "host_boot",
            "interval_seconds",
            "metrics",
            "issues",
            "sources",
            "games",
        }
        or type(sample["schema"]) is not int
        or sample["schema"] != 1
        or type(sample["at"]) is not int
        or not 0 <= sample["at"] <= 32_503_680_000
        or type(sample["sequence"]) is not int
        or not 1 <= sample["sequence"] <= 10**15
        or not isinstance(sample["collector"], str)
        or not re.fullmatch(r"[a-f0-9]{32}", sample["collector"])
        or not isinstance(sample["host"], str)
        or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", sample["host"])
        or not isinstance(sample["host_boot"], str)
        or not re.fullmatch(r"[a-f0-9-]{36}", sample["host_boot"])
        or not isinstance(sample["config_sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", sample["config_sha256"])
        or not isinstance(sample["metrics"], dict)
        or len(sample["metrics"]) > 1024
    ):
        raise ValueError("Invalid resource sample")
    interval = sample["interval_seconds"]
    if interval is not None and (
        type(interval) not in (int, float)
        or not math.isfinite(interval)
        or not 0 < interval <= 3600
    ):
        raise ValueError("Invalid resource interval")
    for name, value in sample["metrics"].items():
        if (
            not isinstance(name, str)
            or not METRIC.fullmatch(name)
            or type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 10**24
        ):
            raise ValueError("Invalid resource measurement")
    if (
        not isinstance(sample["issues"], list)
        or len(sample["issues"]) > 128
        or any(
            not isinstance(v, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}:(unavailable|stale)", v)
            for v in sample["issues"]
        )
    ):
        raise ValueError("Invalid resource issues")
    for name, pattern in (
        ("sources", r"[a-f0-9]{64}"),
        ("releases", r"[A-Za-z0-9_.+-]{1,80}"),
    ):
        mapping = sample[name]
        if (
            not isinstance(mapping, dict)
            or len(mapping) > 32
            or any(
                not isinstance(k, str)
                or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", k)
                or not isinstance(v, str)
                or not re.fullmatch(pattern, v)
                for k, v in mapping.items()
            )
        ):
            raise ValueError("Invalid resource provenance")
    _game_provenance(sample.get("games", {}))
    raw = json.dumps(sample, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > 128 * 1024:
        raise ValueError("Resource sample exceeds bound")
    return raw


def _game_provenance(games):
    if not isinstance(games, dict) or len(games) > 4:
        raise ValueError("Invalid game metric provenance")
    for label, entry in games.items():
        if (
            not isinstance(label, str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", label)
            or not isinstance(entry, dict)
            or set(entry)
            != {
                "profile",
                "core_version",
                "boot",
                "sequence",
                "sampled_at_ms",
                "running",
                "dimensions_truncated",
            }
        ):
            raise ValueError("Invalid game metric provenance")
        for key, pattern in (
            ("profile", r"[a-z0-9_.-]{1,80}"),
            ("core_version", r"[0-9]+\.[0-9]+\.[0-9]+"),
            ("boot", r"[a-f0-9]{32}"),
        ):
            if not isinstance(entry[key], str) or not re.fullmatch(pattern, entry[key]):
                raise ValueError("Invalid game metric identity")
        if (
            type(entry["sequence"]) is not int
            or not 1 <= entry["sequence"] <= 10**18
            or type(entry["sampled_at_ms"]) is not int
            or not 0 <= entry["sampled_at_ms"] <= 10**18
            or type(entry["running"]) is not bool
            or type(entry["dimensions_truncated"]) is not bool
        ):
            raise ValueError("Invalid game metric provenance values")


class ResourceStore:
    """Detail and hourly min/max/sum/count share a hard SQLite page ceiling.

    A DELETE rollback journal can be as large as the database: reserve/budget two
    database sizes plus 1 MiB. Age/capacity retention never touches other files.
    An active reader may delay a transaction; busy_timeout bounds that wait.
    """

    def __init__(
        self, root, *, database_mib=64, detail_days=7, hourly_days=180, reserve_mib=1024
    ):
        if (
            type(database_mib) is not int
            or not 4 <= database_mib <= 1024
            or type(detail_days) is not int
            or not 1 <= detail_days <= 30
            or type(hourly_days) is not int
            or not detail_days <= hourly_days <= 730
            or type(reserve_mib) is not int
            or not 16 <= reserve_mib <= 1_048_576
        ):
            raise ValueError("Invalid resource history budget")
        self.root = Path(root).absolute()
        self.maximum = database_mib * MIB
        self.detail_days, self.hourly_days = detail_days, hourly_days
        self.reserve = reserve_mib * MIB
        self.database = self.root / "history.sqlite3"
        self.lock = None
        self.db = None
        if self.root.resolve() != self.root or self.root.is_symlink():
            raise ValueError("Linked resource history root")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt" and self.root.stat().st_mode & 0o077:
            raise ValueError("Resource history root requires mode 700")
        try:
            for path in self.root.iterdir():
                if (
                    path.name
                    not in {
                        "history.sqlite3",
                        "history.sqlite3-journal",
                        ".writer.lock",
                    }
                    or not path.is_file()
                    or path.is_symlink()
                    or path.stat().st_nlink != 1
                ):
                    raise ValueError("Unexpected resource history file")
                if os.name != "nt" and path.stat().st_mode & 0o077:
                    raise ValueError("Resource history files require mode 600")
                if path.stat().st_size > self.maximum + MIB:
                    raise ValueError("Resource history exceeds configured budget")
            self.lock = open(  # noqa: SIM115 - lifetime is the store context
                self.root / ".writer.lock", "a+b"
            )
            os.chmod(self.root / ".writer.lock", 0o600)
            if os.name == "posix":
                import fcntl  # noqa: PLC0415

                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt  # noqa: PLC0415

                self.lock.seek(0)
                if not self.lock.read(1):
                    self.lock.write(b"\0")
                    self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            self._space()
            # Create the file privately before SQLite opens it, regardless of umask.
            fd = os.open(
                self.database,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.close(fd)
            self._connect()
        except BaseException:
            self.close()
            raise

    def _connect(self):
        self.db = sqlite3.connect(self.database, timeout=2)
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA cache_size=-2048")
        self.db.execute("PRAGMA journal_size_limit=0")
        self.db.execute("PRAGMA trusted_schema=OFF")
        self.db.execute("PRAGMA page_size=4096")
        page_size = self.db.execute("PRAGMA page_size").fetchone()[0]
        if (
            self.db.execute(
                "PRAGMA max_page_count=" + str(self.maximum // page_size)
            ).fetchone()[0]
            * page_size
            > self.maximum
        ):
            raise ValueError("Existing resource database exceeds budget")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise ValueError("Unknown resource history schema")
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS samples(at INTEGER NOT NULL, "
                "collector TEXT NOT NULL, sequence INTEGER NOT NULL, payload TEXT NOT NULL, "
                "PRIMARY KEY(collector,sequence))"
            )
            self.db.execute("CREATE INDEX IF NOT EXISTS samples_time ON samples(at)")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS hours(hour INTEGER NOT NULL, "
                "host TEXT NOT NULL, config TEXT NOT NULL, count INTEGER NOT NULL, "
                "issues INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(hour,host,config))"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS clock(id INTEGER PRIMARY KEY CHECK(id=1), "
                "latest INTEGER NOT NULL, collector TEXT NOT NULL, sequence INTEGER NOT NULL, "
                "sha256 TEXT NOT NULL)"
            )
            self.db.execute("PRAGMA user_version=1")

    def _space(self):
        # Covers a worst-case full rollback journal plus the owner's free reserve.
        if shutil.disk_usage(self.root).free < self.reserve + self.maximum + MIB:
            raise OSError("Resource history free-space reserve reached")

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.lock is not None:
            self.lock.close()
            self.lock = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def append(self, sample):
        raw = validate_sample(sample)
        self._space()
        at, host, config = sample["at"], sample["host"], sample["config_sha256"]
        existing = self.db.execute(
            "SELECT payload FROM samples WHERE collector=? AND sequence=?",
            (sample["collector"], sample["sequence"]),
        ).fetchone()
        if existing:
            if existing[0] != raw:
                raise ValueError("Resource sample identity conflict")
            return False
        latest = self.db.execute(
            "SELECT latest,collector,sequence,sha256 FROM clock WHERE id=1"
        ).fetchone()
        digest = hashlib.sha256(raw.encode()).hexdigest()
        if (
            latest
            and latest[1] == sample["collector"]
            and sample["sequence"] <= latest[2]
        ):
            if sample["sequence"] == latest[2] and digest == latest[3]:
                return False
            raise ValueError("Resource sample sequence moved backwards or conflicted")
        if latest and at < latest[0]:
            raise ValueError("Resource history clock moved backwards")
        hour = at - at % 3600
        previous = self.db.execute(
            "SELECT count,issues,payload FROM hours WHERE hour=? AND host=? AND config=?",
            (hour, host, config),
        ).fetchone()
        gauges = {} if previous is None else json.loads(previous[2])
        for name, value in sample["metrics"].items():
            if name not in gauges:
                gauges[name] = [1, value, value, value]
            else:
                gauge = gauges[name]
                gauge[:] = [
                    gauge[0] + 1,
                    min(gauge[1], value),
                    max(gauge[2], value),
                    gauge[3] + value,
                ]
        payload = json.dumps(
            gauges, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        # Metric cardinality cannot grow without bound inside a reused config hash.
        if len(gauges) > 1024 or len(payload) > 256 * 1024:
            raise ValueError("Hourly resource aggregate exceeds bound")
        # Keep the database below 75% occupied pages, leaving room for the next
        # transaction. Old detail goes first, then oldest hourly aggregates.
        # Pruning commits separately: an interrupted append loses a sample, never
        # creates a half detail/hour pair. The surviving hour is still truthful.
        with self.db:
            self.db.execute(
                "DELETE FROM samples WHERE at < ?", (at - self.detail_days * 86400,)
            )
            self.db.execute(
                "DELETE FROM hours WHERE hour < ?", (hour - self.hourly_days * 86400,)
            )
        pages = self.db.execute("PRAGMA page_count").fetchone()[0]
        free = self.db.execute("PRAGMA freelist_count").fetchone()[0]
        page_size = self.db.execute("PRAGMA page_size").fetchone()[0]
        while (pages - free) * page_size > self.maximum * 0.75:
            with self.db:
                changed = self.db.execute(
                    "DELETE FROM samples WHERE rowid IN (SELECT rowid FROM samples ORDER BY at LIMIT 256)"
                ).rowcount
                if not changed:
                    changed = self.db.execute(
                        "DELETE FROM hours WHERE rowid IN (SELECT rowid FROM hours ORDER BY hour LIMIT 24)"
                    ).rowcount
            if not changed:
                raise ValueError("Resource database has no evictable history")
            free = self.db.execute("PRAGMA freelist_count").fetchone()[0]
        with self.db:
            self.db.execute(
                "INSERT INTO samples VALUES(?,?,?,?)",
                (at, sample["collector"], sample["sequence"], raw),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO hours VALUES(?,?,?,?,?,?)",
                (
                    hour,
                    host,
                    config,
                    1 if previous is None else previous[0] + 1,
                    len(sample["issues"]) + (0 if previous is None else previous[1]),
                    payload,
                ),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO clock VALUES(1,?,?,?,?)",
                (at, sample["collector"], sample["sequence"], digest),
            )
        return True


def hourly_report(database, *, since, until, max_rows=1000, max_bytes=2 * MIB):
    """Read-only bounded owner/TUI API; no HTTP endpoint or player command."""
    if (
        type(since) is not int
        or type(until) is not int
        or not 0 <= since < until
        or type(max_rows) is not int
        or not 1 <= max_rows <= 10000
        or type(max_bytes) is not int
        or not 65536 <= max_bytes <= 8 * MIB
    ):
        raise ValueError("Invalid resource report range")
    path = Path(database).absolute()
    if path.resolve() != path or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Missing or linked resource database")
    with contextlib.closing(
        sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
    ) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("Unknown resource history schema")
        # Include intersecting hours, explicitly reporting whole-hour aggregates.
        cursor = db.execute(
            "SELECT hour,host,config,count,issues,payload FROM hours "
            "WHERE hour >= ? AND hour < ? ORDER BY hour,host,config LIMIT ?",
            (since - since % 3600, until, max_rows + 1),
        )
        rows, size, truncated = [], 0, False
        for row in cursor:
            size += len(row[5])
            if len(rows) == max_rows or size > max_bytes:
                truncated = True
                break
            rows.append(row)
        return {
            "schema": 1,
            "resolution": "whole_hour",
            "requested_since": since,
            "requested_until": until,
            "truncated": truncated,
            "hours": [
                {
                    "at": row[0],
                    "host": row[1],
                    "config_sha256": row[2],
                    "samples": row[3],
                    "unavailable_sections": row[4],
                    "metrics": {
                        name: {
                            "count": v[0],
                            "min": v[1],
                            "max": v[2],
                            "mean": v[3] / v[0],
                        }
                        for name, v in json.loads(row[5]).items()
                    },
                }
                for row in rows[:max_rows]
            ],
        }
