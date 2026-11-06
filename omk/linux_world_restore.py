"""Stage a verified world on an explicitly initialized, stopped Linux target.

No Docker socket, lifecycle, overwrites, credential restore or automatic retry.
The owner orchestrator mounts the selected store readonly and a fresh owned volume.
"""

import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

from omk.backup_archive import regular_file, verify_archive
from omk.backup_store import (
    BackupPolicy,
    BackupStore,
    _directory,
    _json_write,
    _sync_directory,
)
from omk.stopped_world_backup import inventory

OWNER = ".omk-world-stage-owner.json"
PLAN = ".omk-world-stage-plan.json"
DONE = ".omk-world-staged.json"
POLICY_MARKERS = (".omk-current-policy-plan.json", ".omk-current-policy-staged.json")


def _read(path):
    try:
        size = regular_file(path)
    except OSError:
        raise ValueError("World stage metadata is missing") from None
    if size > 65536:
        raise ValueError("World stage metadata exceeds limit")
    return json.loads(path.read_bytes())


def _request(request, target):
    if sys.platform != "linux":
        raise ValueError("Linux server world extraction requires Linux")
    _directory(target)
    if not re.fullmatch(
        r"[a-f0-9]{32}", request.get("operation", "")
    ) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request.get("world", "")):
        raise ValueError("Invalid owned world stage identity")
    return {"schema": 1, "operation": request["operation"], "world": request["world"]}


def _selected(request, storage):
    store = BackupStore(
        storage,
        BackupPolicy(**request["policy"]),
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    archive, manifest = store.readonly_snapshot(request["snapshot"])
    if (
        manifest["sha256"] != request["archive_sha256"]
        or request["world"] + "/level.dat" not in manifest["files"]
        or any(
            not name.startswith(request["world"] + "/") for name in manifest["files"]
        )
    ):
        raise ValueError("World stage snapshot/hash/root mismatch")
    return archive, manifest


def _copy(archive, name, target, expected):
    path = target.joinpath(*name.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest, length = hashlib.sha256(), 0
    with archive.open(name) as source, path.open("xb") as output:
        path.chmod(0o600)
        while data := source.read(1024**2):
            length += len(data)
            if length > expected["bytes"]:
                raise ValueError("Staged world file exceeded size")
            digest.update(data)
            output.write(data)
        output.flush()
        os.fsync(output.fileno())
    with path.open("rb") as file:
        readback = hashlib.file_digest(file, "sha256").hexdigest()
    if (
        length != expected["bytes"]
        or digest.hexdigest() != expected["sha256"]
        or readback != expected["sha256"]
    ):
        raise ValueError("Staged world file failed hash readback")
    parent = path.parent
    while parent.is_relative_to(target):
        _sync_directory(parent)
        if parent == target:
            break
        parent = parent.parent


def execute(request, storage=Path("/backup/store"), target=Path("/restore")):
    identity = _request(request, target)
    world = target / identity["world"]
    if request["action"] == "initialize":
        if (
            world.exists()
            or world.is_symlink()
            or any(
                (target / key).exists() or (target / key).is_symlink()
                for key in (OWNER, PLAN, DONE)
            )
        ):
            raise ValueError(
                "World stage target was already initialized or contains a world"
            )
        _json_write(target / OWNER, identity)
        _sync_directory(target)
        return {"initialized": True}
    if _read(target / OWNER) != identity:
        raise ValueError("World stage ownership mismatch")
    archive, manifest = _selected(request, storage)
    plan = {
        **identity,
        "snapshot": request["snapshot"],
        "sha256": manifest["sha256"],
        "files": len(manifest["files"]),
        "inventory_sha256": hashlib.sha256(
            json.dumps(manifest["files"], sort_keys=True).encode()
        ).hexdigest(),
    }
    if request["action"] == "stage":
        if (
            world.exists()
            or world.is_symlink()
            or any(
                (target / key).exists() or (target / key).is_symlink()
                for key in (PLAN, DONE)
            )
        ):
            raise ValueError(
                "World stage requires a new empty world; never repeat partial extraction"
            )
        required = (
            sum(row["bytes"] for row in manifest["files"].values())
            + 4096 * len(manifest["files"])
            + 65536
        )
        if (
            shutil.disk_usage(target).free
            < required + request["policy"]["reserve_bytes"]
        ):
            raise OSError("World stage free-space reserve would be violated")
        _json_write(target / PLAN, plan)
        _sync_directory(target)
        world.mkdir(mode=0o700)
        with zipfile.ZipFile(archive) as source:
            for name, expected in manifest["files"].items():
                _copy(source, name, target, expected)
        _verify(world, archive, manifest, request)
        _json_write(target / DONE, plan)
        _sync_directory(target)
        return {"staged": True, **plan}
    if request["action"] == "verify":
        if any(
            (target / name).exists() or (target / name).is_symlink()
            for name in POLICY_MARKERS
        ):
            raise ValueError(
                "Current-policy operation requires its full policy verifier"
            )
        if _read(target / PLAN) != plan or _read(target / DONE) != plan:
            raise ValueError("World stage has no complete bound receipt")
        _verify(world, archive, manifest, request)
        return {"verified": True, **plan}
    raise ValueError("Unknown world stage action")


def _verify(world, archive, manifest, request):
    files = inventory(
        world,
        world_name=request["world"],
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    if files != manifest["files"]:
        raise ValueError("World stage inventory differs from verified source")
    verify_archive(
        archive,
        files,
        request["archive_sha256"],
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("World stage request exceeds limit")
        print(json.dumps({"ok": True, **execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
