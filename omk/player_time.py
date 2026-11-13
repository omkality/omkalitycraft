"""Owner-only bounded view of saved vanilla ticks on the allowlisted Linux source."""

import json
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
)
from omk.admin import AdminError
from omk.profiles import PROJECT_ROOT

LABEL = "omkality.playtime.query"


def validate_data(data, player):
    base = {"schema", "player_uuid", "source", "available"}
    if (
        not isinstance(data, dict)
        or type(data.get("schema")) is not int
        or data.get("schema") != 1
        or data.get("player_uuid") != player
        or data.get("source") != "forge112_saved_stat_play_one_minute"
        or type(data.get("available")) is not bool
    ):
        raise AdminError("Invalid saved-time response identity")
    if data["available"]:
        expected = base | {
            "ticks",
            "nominal_seconds_at_20_tps",
            "wall_clock_seconds",
            "afk_excluded",
            "live_unsaved_ticks_included",
            "file_mtime_ns",
        }
        if (
            set(data) != expected
            or type(data["ticks"]) is not int
            or not 0 <= data["ticks"] <= 2**31 - 1
            or type(data["nominal_seconds_at_20_tps"]) not in {int, float}
            or data["nominal_seconds_at_20_tps"] != data["ticks"] / 20
            or data["wall_clock_seconds"] is not None
            or data["afk_excluded"] is not False
            or data["live_unsaved_ticks_included"] is not False
        ):
            raise AdminError("Invalid saved-time counter or semantics")
    elif data.get("reason") == "no_saved_statistics":
        if set(data) != base | {"reason"}:
            raise AdminError("Invalid missing-statistics response")
    elif data.get("reason") == "statistic_not_recorded":
        if set(data) != base | {"reason", "file_mtime_ns"}:
            raise AdminError("Invalid unrecorded-statistics response")
    else:
        raise AdminError("Unknown saved-time coverage")
    if "file_mtime_ns" in data and type(data["file_mtime_ns"]) is not int:
        raise AdminError("Invalid saved-time file metadata")
    return data


def settings(environment=None):
    env = os.environ if environment is None else environment
    result = {}
    for key, default, low, high in (
        ("INPUT_MIB", 4, 1, 16),
        ("TIMEOUT_SECONDS", 30, 5, 120),
    ):
        name = "OMK_PLAYTIME_" + key
        raw = env.get(name, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 3
            or not low <= int(raw) <= high
        ):
            raise AdminError("Invalid " + name)
        result[key.lower()] = int(raw)
    return result


def _cleanup(name, operation):
    raw = backups.docker("inspect", "--type", "container", name, allowed_codes=(0, 1))
    if not raw.strip():
        return
    rows = json.loads(raw)
    if (
        len(rows) != 1
        or rows[0]["Config"].get("Labels", {}).get(LABEL) != operation
        or rows[0]["Config"]["Image"] != backups.IMAGE
    ):
        raise AdminError("Saved-time helper ownership changed")
    backups.docker("rm", "--force", rows[0]["Id"])


def _worker(target, player, policy, resources):
    operation = uuid4().hex
    name = "omk-playtime-" + operation
    request = {
        "world": target["world"],
        "player": player,
        "limit_bytes": policy["input_mib"] * 1024**2,
    }
    args = [
        "run",
        "--pull",
        "never",
        "-i",
        "--name",
        name,
        "--label",
        LABEL + "=" + operation,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        str(resources["helper_memory_mib"]) + "m",
        "--cpus",
        str(resources["helper_cpus"]),
        "--pids-limit",
        "32",
        "--mount",
        f"type=volume,source={target['data_volume']},target=/server,readonly",
        "--mount",
        f"type=bind,source={PROJECT_ROOT/'omk'},target=/src/omk,readonly",
        "--mount",
        f"type=bind,source={PROJECT_ROOT/'profiles/runtime'},target=/src/profiles/runtime,readonly",
        "--workdir",
        "/src",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        backups.IMAGE,
        "python",
        "-m",
        "omk.player_time_reader",
    ]
    try:
        raw = backups.docker(
            *args,
            stdin=json.dumps(request),
            timeout=policy["timeout_seconds"],
            allowed_codes=(0, 1),
        )
        if len(raw.encode("utf-8")) > 16384:
            raise AdminError("Saved-time response exceeded bound")
        result = json.loads(raw)
        if (
            not isinstance(result, dict)
            or set(result) != {"ok", "data"}
            or result["ok"] is not True
        ):
            raise AdminError(
                "Saved-time source is unreadable, unreviewed or changed; no zero was inferred"
            )
        return validate_data(result["data"], player)
    finally:
        _cleanup(name, operation)


def saved_playtime(config, server, player, environment=None):
    try:
        player = str(UUID(player))
    except ValueError, TypeError, AttributeError:
        raise AdminError(
            "Use the player's account UUID, not a nickname or path"
        ) from None
    policy = settings(environment)
    resources = backups.settings(environment)
    with backups.locked(config):
        backups.local_engine()
        target = backups.target_for(config, server)
        endpoint = maintenance.binding(config, server)
        before = maintenance.snapshot(target, endpoint)
        data = _worker(target, player, policy, resources)
        if maintenance.snapshot(target, endpoint) != before:
            raise AdminError(
                "Server identity or lifecycle changed during saved-time read; retry"
            )
    return {
        "ok": True,
        "server": server,
        "release": target["release"],
        "running": before["running"],
        "observed_at": datetime.now(UTC).isoformat(),
        "snapshot_dependent": True,
        "account_lifetime": False,
        "nominal_hours_at_20_tps": data["ticks"] / 72000 if data["available"] else None,
        **data,
    }
