"""Bounded metadata-only accounting of explicitly mounted owner volumes."""

import json
import os
import re
import stat
import sys
from pathlib import Path

ROLES = {"source", "store", "reset", "restore"}


def category(role, parts, world):
    if role != "source":
        return role
    return {
        world: "active_world",
        ".omk-cutovers": "retained_world_generations",
        "logs": "game_logs",
        "crash-reports": "crash_reports",
        "backups": "pack_backups",
    }.get(parts[0] if parts else "", "runtime_and_other")


def stamp(value):
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def scan(root, role, world, limits, seen, snapshots):
    buckets = {}
    device = root.lstat().st_dev
    stack = [(root, ())]
    while stack:
        path, parts = stack.pop()
        value = path.lstat()
        if path.is_symlink() or path.is_junction() or value.st_dev != device:
            raise ValueError("Linked or nested storage mount is unsupported")
        is_dir = stat.S_ISDIR(value.st_mode)
        if not is_dir and (not stat.S_ISREG(value.st_mode) or value.st_nlink != 1):
            raise ValueError("Storage contains a special or multiply linked file")
        identity = (value.st_dev, value.st_ino)
        if identity in seen:
            raise ValueError("Storage roots or files alias")
        seen.add(identity)
        snapshots.append((path, stamp(value)))
        if len(seen) > limits["max_entries"] or len(parts) > limits["max_depth"]:
            raise ValueError("Storage inventory exceeds its configured bound")
        bucket = buckets.setdefault(
            category(role, parts, world),
            {
                "files": 0,
                "directories": 0,
                "apparent_bytes": 0,
                "allocated_bytes": 0,
            },
        )
        bucket["directories" if is_dir else "files"] += 1
        bucket["apparent_bytes"] += 0 if is_dir else value.st_size
        bucket["allocated_bytes"] += value.st_blocks * 512
        if is_dir:
            with os.scandir(path) as entries:
                for entry in entries:
                    stack.append((path / entry.name, (*parts, entry.name)))
                    if len(stack) + len(seen) > limits["max_entries"]:
                        raise ValueError(
                            "Storage inventory exceeds its configured bound"
                        )
    return {"role": role, "categories": buckets}, device


def execute(request, base=Path("/storage")):
    if (
        not isinstance(request, dict)
        or set(request) != {"schema", "roles", "world", "limits"}
        or type(request["schema"]) is not int
        or request["schema"] != 1
        or not isinstance(request["roles"], list)
        or not 2 <= len(request["roles"]) <= 4
        or len(set(request["roles"])) != len(request["roles"])
        or set(request["roles"]) - ROLES
        or not {"source", "store"} <= set(request["roles"])
        or not isinstance(request["world"], str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request["world"])
        or not isinstance(request["limits"], dict)
        or set(request["limits"]) != {"max_entries", "max_depth"}
        or any(type(v) is not int or v < 1 for v in request["limits"].values())
        or request["limits"]["max_entries"] > 1000000
        or request["limits"]["max_depth"] > 128
    ):
        raise ValueError("Invalid storage inventory request")
    seen, snapshots, resources, groups = set(), [], [], {}
    for role in request["roles"]:
        root = base / role
        if root.resolve() != root.absolute() or not root.is_dir():
            raise ValueError("Storage root must be an ordinary absolute directory")
        before = os.statvfs(root)
        resource, device = scan(
            root, role, request["world"], request["limits"], seen, snapshots
        )
        after = os.statvfs(root)
        group = groups.setdefault(
            device,
            {
                "roles": [],
                "total_bytes": after.f_blocks * after.f_frsize,
                "available_bytes": min(
                    before.f_bavail * before.f_frsize, after.f_bavail * after.f_frsize
                ),
            },
        )
        group["roles"].append(role)
        group["available_bytes"] = min(
            group["available_bytes"],
            before.f_bavail * before.f_frsize,
            after.f_bavail * after.f_frsize,
        )
        resources.append(resource)
    for path, expected in snapshots:
        if stamp(path.lstat()) != expected:
            raise ValueError(
                "Storage changed during inventory; retry in a quiet window"
            )
    return {
        "schema": 1,
        "resources": resources,
        "filesystems": list(groups.values()),
        "read_only": True,
        "metadata_only": True,
        "atomic_snapshot": False,
        "host_disk_complete": False,
        "backup_integrity_verified": False,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            raise ValueError("Storage inventory request exceeds bound")
        print(json.dumps({"ok": True, "result": execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
