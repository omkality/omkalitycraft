"""Read saved Forge 1.12.2 play ticks; never count sessions or write game state."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from uuid import UUID

from omk.fs import regular
from omk.profiles import PROJECT_ROOT


def runtime_pin():
    return json.loads(
        (PROJECT_ROOT / "profiles/runtime/forge112-server.json").read_text(
            encoding="utf-8"
        )
    )["forge"]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate statistics key")
        result[key] = value
    return result


def read_saved(request, root=Path("/server")):
    if not isinstance(request, dict) or set(request) != {
        "world",
        "player",
        "limit_bytes",
    }:
        raise ValueError("Invalid saved-time request")
    world, player, limit = request["world"], request["player"], request["limit_bytes"]
    if (
        not isinstance(world, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", world)
        or not isinstance(player, str)
        or str(UUID(player)) != player
        or type(limit) is not int
        or not 1024**2 <= limit <= 16 * 1024**2
    ):
        raise ValueError("Invalid saved-time identity or bound")
    pin = runtime_pin()
    artifact = root / pin["path"]
    if not regular(artifact, root) or artifact.stat().st_size > 16 * 1024**2:
        raise ValueError("Reviewed Forge runtime is missing or linked")
    with artifact.open("rb") as stream:
        data = stream.read(16 * 1024**2 + 1)
        if (
            len(data) > 16 * 1024**2
            or hashlib.sha256(data).hexdigest() != pin["sha256"]
        ):
            raise ValueError("Reviewed Forge runtime mismatch")
    if (
        (root / world).is_symlink()
        or (root / world).is_junction()
        or not (root / world).is_dir()
    ):
        raise ValueError("Invalid statistics world directory")
    folder = root / world / "stats"
    if folder.is_symlink() or folder.is_junction():
        raise ValueError("Linked statistics directory")
    path = folder / (player + ".json")
    base = {
        "schema": 1,
        "player_uuid": player,
        "source": "forge112_saved_stat_play_one_minute",
        "available": False,
    }
    if not path.exists() and not path.is_symlink():
        return {**base, "reason": "no_saved_statistics"}
    if not regular(path, root) or path.stat().st_size > limit:
        raise ValueError("Linked or oversized player statistics")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())

    def identity(st):
        return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)

    if (
        len(raw) > limit
        or identity(before) != identity(after)
        or identity(path.stat()) != identity(after)
    ):
        raise ValueError("Player statistics changed during read")
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("Invalid saved statistics document")
    if "stat.playOneMinute" not in value:
        return {
            **base,
            "reason": "statistic_not_recorded",
            "file_mtime_ns": after.st_mtime_ns,
        }
    ticks = value["stat.playOneMinute"]
    if type(ticks) is not int or not 0 <= ticks <= 2**31 - 1:
        raise ValueError("Invalid or overflowed saved play ticks")
    return {
        **base,
        "available": True,
        "ticks": ticks,
        "nominal_seconds_at_20_tps": ticks / 20,
        "wall_clock_seconds": None,
        "afk_excluded": False,
        "live_unsaved_ticks_included": False,
        "file_mtime_ns": after.st_mtime_ns,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise ValueError("Oversized saved-time request")
        print(json.dumps({"ok": True, "data": read_saved(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
