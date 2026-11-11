"""Metadata-only project volume census, sharing the bounded filesystem walker."""

import json
import os
import re
import sys
from pathlib import Path

from omk.storage_inventory import scan, stamp

ROLES = {"source", "store", "reset", "restore", "auth", "content", "reports", "exports"}


def validate(request):
    if (
        not isinstance(request, dict)
        or set(request) != {"schema", "resources", "limits"}
        or type(request["schema"]) is not int
        or request["schema"] != 1
        or not isinstance(request["resources"], list)
        or not 3 <= len(request["resources"]) <= 64
        or not isinstance(request["limits"], dict)
        or set(request["limits"]) != {"max_entries", "max_depth"}
        or any(type(v) is not int or v < 1 for v in request["limits"].values())
        or request["limits"]["max_entries"] > 1000000
        or request["limits"]["max_depth"] > 128
    ):
        raise ValueError("Invalid project storage inventory request")
    identifiers, roles = set(), set()
    for entry in request["resources"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"id", "role", "world"}
            or not isinstance(entry["id"], str)
            or not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", entry["id"])
            or entry["id"] in identifiers
            or entry["role"] not in ROLES
            or not isinstance(entry["world"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", entry["world"])
        ):
            raise ValueError("Invalid project storage resource")
        identifiers.add(entry["id"])
        roles.add(entry["role"])
    if not {"source", "store", "auth"} <= roles:
        raise ValueError("Project inventory requires game, backup and auth volumes")


def execute(request, base=Path("/storage")):
    validate(request)
    seen, snapshots, resources, groups = set(), [], [], {}
    for entry in request["resources"]:
        root = base / entry["id"]
        if root.resolve() != root.absolute() or not root.is_dir():
            raise ValueError("Project storage root is missing or linked")
        before = os.statvfs(root)
        resource, device = scan(
            root, entry["role"], entry["world"], request["limits"], seen, snapshots
        )
        after = os.statvfs(root)
        group = groups.setdefault(
            device,
            {
                "resources": [],
                "total_bytes": after.f_blocks * after.f_frsize,
                "available_bytes": before.f_bavail * before.f_frsize,
            },
        )
        group["resources"].append(entry["id"])
        group["available_bytes"] = min(
            group["available_bytes"],
            before.f_bavail * before.f_frsize,
            after.f_bavail * after.f_frsize,
        )
        resources.append({**resource, "id": entry["id"]})
    for path, expected in snapshots:
        if stamp(path.lstat()) != expected:
            raise ValueError("Project storage changed during observation")
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
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ValueError("Project storage request exceeds bound")
        print(json.dumps({"ok": True, "result": execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
