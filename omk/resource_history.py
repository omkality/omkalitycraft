"""Private Linux resource collector entry point; installs no host jobs or services."""

import hashlib
import json
import os
import signal
import sqlite3
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

from omk.game_metrics import GameMetrics
from omk.resource_metrics import LinuxMetrics, read, validate_config
from omk.resource_store import ResourceStore


def settings(environ=None):
    environment = os.environ if environ is None else environ
    result = {}
    for key, default, minimum, maximum in (
        ("INTERVAL_SECONDS", 30, 10, 300),
        ("DATABASE_MIB", 64, 4, 1024),
        ("DETAIL_DAYS", 7, 1, 30),
        ("HOURLY_DAYS", 180, 1, 730),
        ("RESERVE_MIB", 1024, 16, 1048576),
    ):
        value = environment.get("OMK_METRICS_" + key, str(default))
        if (
            not isinstance(value, str)
            or not value.isascii()
            or not value.isdecimal()
            or len(value) > 7
            or not minimum <= int(value) <= maximum
        ):
            raise ValueError("Invalid resource history setting: " + key)
        result[key.lower()] = int(value)
    if result["detail_days"] > result["hourly_days"]:
        raise ValueError("Hourly retention must cover detail retention")
    return result


def run(config_path, root, *, policy=None, stop=None):
    if sys.platform != "linux":
        raise ValueError("Resource collection requires Linux cgroup v2")
    policy = settings() if policy is None else policy
    raw = read(config_path)
    if len(raw) > 16384:
        raise ValueError("Resource configuration exceeds bound")
    config = validate_config(json.loads(raw))
    config_hash = hashlib.sha256(raw.encode("ascii")).hexdigest()
    interval = policy["interval_seconds"]
    collector = LinuxMetrics(config, max_gap=interval * 3)
    games = GameMetrics(config.get("games", {}))
    identity, sequence = uuid4().hex, 0
    stop = threading.Event() if stop is None else stop
    with ResourceStore(
        root, **{k: v for k, v in policy.items() if k != "interval_seconds"}
    ) as store:
        while not stop.is_set():
            start = time.monotonic()
            sample = collector.sample(start)
            game = games.sample(int(time.time() * 1000))
            sample["metrics"].update(game["metrics"])
            sample["issues"].extend(game["issues"])
            sample["games"] = game["games"]
            sequence += 1
            store.append(
                {
                    "schema": 1,
                    "at": int(time.time()),
                    "collector": identity,
                    "sequence": sequence,
                    "host": config["host"],
                    "config_sha256": config_hash,
                    "releases": {
                        k: v["release"] for k, v in config["services"].items()
                    },
                    **sample,
                }
            )
            # No catch-up burst after slow I/O or suspension.
            stop.wait(max(0.1, interval - (time.monotonic() - start)))


def main():
    stop = threading.Event()
    for kind in (signal.SIGINT, signal.SIGTERM):
        signal.signal(kind, lambda *_: stop.set())
    try:
        if sys.argv[1:] == ["health"]:
            return 0 if healthy(Path("/history/history.sqlite3")) else 1
        if sys.argv[1:]:
            return 2
        run(Path("/run/metrics/config.json"), Path("/history"), stop=stop)
    except Exception as error:
        # No secret-bearing values, exception text, filesystem paths or traceback.
        print("Resource history stopped: " + type(error).__name__, file=sys.stderr)
        return 1
    return 0


def healthy(database, *, now=None, interval=None):
    """No writes or lock ownership; a database's mere existence is not health."""
    path = Path(database).absolute()
    if not path.is_file() or path.resolve() != path or path.stat().st_nlink != 1:
        return False
    interval = settings()["interval_seconds"] if interval is None else interval
    now = time.time() if now is None else now
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            row = connection.execute("SELECT latest FROM clock WHERE id=1").fetchone()
            return row is not None and 0 <= now - row[0] <= interval * 3
        finally:
            connection.close()
    except sqlite3.Error:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
