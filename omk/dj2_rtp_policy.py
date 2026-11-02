"""Validated, exclusive offline RTP policy creation; never edits a running server."""

import json
import os
import re
from pathlib import Path

from omk.profiles import PROJECT_ROOT

POLICY_FILE = "omkalitycore-rtp.properties"
DEFAULT_PROFILE = PROJECT_ROOT / "profiles/server-defaults/dj2/rtp.json"


def _number(values, key, default, low, high):
    value = values.get(key, str(default))
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,6}", value):
        raise ValueError(f"Invalid {key}")
    result = int(value)
    if not low <= result <= high:
        raise ValueError(f"Invalid {key}")
    return result


def _worlds(path):
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 4096:
            raise ValueError
        profile = json.loads(path.read_bytes())
        if (
            set(profile) != {"version", "worlds"}
            or type(profile["version"]) is not int
            or profile["version"] != 1
        ):
            raise ValueError
        rows = profile["worlds"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
            raise ValueError
        ids = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "id",
                "mode",
                "min_y",
                "max_y",
            }:
                raise ValueError
            if (
                type(row["id"]) is not int
                or not -9999999 <= row["id"] <= 9999999
                or row["id"] in ids
                or row["mode"] not in ("surface", "cave")
                or type(row["min_y"]) is not int
                or type(row["max_y"]) is not int
                or not 1 <= row["min_y"] <= 252
                or not 2 <= row["max_y"] <= 253
                or row["min_y"] > row["max_y"]
            ):
                raise ValueError
            ids.add(row["id"])
        return rows
    except OSError, ValueError, TypeError, KeyError:
        raise ValueError("Invalid OMK_DJ2_RTP_PROFILE") from None


def write_rtp_policy(config_directory: Path, environ=None):
    values = os.environ if environ is None else environ
    minimum = _number(values, "OMK_DJ2_RTP_MIN_DISTANCE", 1000, 0, 100000)
    maximum = _number(values, "OMK_DJ2_RTP_MAX_DISTANCE", 5461, 1, 100000)
    percent = _number(values, "OMK_DJ2_RTP_BORDER_PERCENT", 66, 10, 90)
    attempts = _number(values, "OMK_DJ2_RTP_ATTEMPTS", 64, 1, 256)
    loads = _number(values, "OMK_DJ2_RTP_CHUNK_LOADS", 8, 1, 16)
    retry = _number(values, "OMK_DJ2_RTP_RETRY_SECONDS", 5, 2, 60)
    if minimum >= maximum:
        raise ValueError("Invalid RTP distance range")
    rows = _worlds(Path(values.get("OMK_DJ2_RTP_PROFILE", DEFAULT_PROFILE)))
    folder = Path(config_directory)
    if not folder.is_dir() or any(p.is_symlink() for p in (folder, *folder.parents)):
        raise ValueError("A real offline config directory is required")
    worlds = ";".join(f'{r["id"]}:{r["mode"]}:{r["min_y"]}:{r["max_y"]}' for r in rows)
    with (folder / POLICY_FILE).open("x", encoding="ascii", newline="\n") as file:
        file.write(
            f"version=1\nminimum={minimum}\nmaximum={maximum}\nborder_percent={percent}\n"
            f"attempts={attempts}\nchunk_loads={loads}\nretry_seconds={retry}\nworlds={worlds}\n"
        )
    return {
        "minimum": minimum,
        "maximum": maximum,
        "border_percent": percent,
        "attempts": attempts,
        "chunk_loads": loads,
        "retry_seconds": retry,
        "worlds": rows,
    }
