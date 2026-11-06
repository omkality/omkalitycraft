"""Bounded snapshot of a stopped world into the managed archive transaction.

The caller must hold the server offline. This module does not stop a live server,
adopt an FTB backup directory, schedule jobs, or restore/publish a game service.
"""

import hashlib
import json
import os
import shutil
import zipfile
from dataclasses import replace
from pathlib import Path

from omk.backup_archive import (
    MAX_EXPANDED_BYTES,
    MAX_FILES,
    regular_file,
    validate_inventory,
)
from omk.backup_store import BackupPolicy, BackupStore

LAB_POLICY = BackupPolicy(
    max_bytes=128 * 1024**2,
    max_count=4,
    staging_bytes=64 * 1024**2,
    reserve_bytes=32 * 1024**2,
)


def inventory(world):
    if world.name != "lab-world" or world.is_symlink() or not world.is_dir():
        raise ValueError("Expected a stopped lab-world directory")
    result, size = {}, 0
    for directory, folders, filenames in os.walk(world, followlinks=False):
        base = Path(directory)
        if any((base / folder).is_symlink() for folder in folders):
            raise ValueError("Linked world directory")
        for filename in sorted(filenames):
            path = base / filename
            length = regular_file(path)
            size += length
            if len(result) >= MAX_FILES or size > MAX_EXPANDED_BYTES:
                raise ValueError("World exceeds snapshot budget")
            with path.open("rb") as file:
                result[path.relative_to(world.parent).as_posix()] = {
                    "bytes": length,
                    "sha256": hashlib.file_digest(file, "sha256").hexdigest(),
                }
    if "lab-world/level.dat" not in result:
        raise ValueError("World has no level marker")
    validate_inventory(result)
    return result


def snapshot(world, storage, policy):
    files = inventory(world)  # Independent of the ZIP and its own manifest.
    staging = storage / "incoming.zip"
    if staging.exists():
        raise ValueError("Interrupted staging requires operator inspection")
    # Worst-case ZIP overhead + two manifests. No optimistic compression assumption.
    overhead = 2 * 8 * 1024**2 + len(files) * 2048
    required = sum(row["bytes"] for row in files.values()) + overhead
    if required > policy.staging_bytes:
        raise ValueError("Uncompressed world exceeds staging budget")
    if shutil.disk_usage(storage).free < required * 2 + policy.reserve_bytes:
        raise OSError("Free-space reserve would be violated")
    root = storage / "store"
    store = (
        BackupStore(root, policy) if root.exists() else BackupStore.create(root, policy)
    )
    with staging.open("xb") as output:
        with zipfile.ZipFile(
            output, "w", zipfile.ZIP_DEFLATED, compresslevel=1
        ) as archive:
            for name in sorted(files):
                archive.write(world.parent / name, name)
        output.flush()
        os.fsync(output.fileno())
    if inventory(world) != files:
        raise ValueError("Stopped world changed while snapshot was prepared")
    published = store.publish(staging, files)
    staging.unlink()  # Only this known input, after verified publication/retention.
    return {
        **published,
        "inventory_files": len(files),
        "inventory_sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True).encode()
        ).hexdigest(),
        "uncompressed_bytes": sum(row["bytes"] for row in files.values()),
        "snapshots": store.inspect(),
    }


def fault_and_retention(world, storage, policy):
    store = BackupStore(storage / "store", policy)
    before = store.inspect()
    if len(before) != policy.max_count:
        raise ValueError("Retention probe requires a full owned history")
    selected = storage / "store" / before[-1]["id"] / "archive.zip"
    manifest = json.loads(selected.with_name("manifest.json").read_bytes())
    candidate = storage / "quota-probe.zip"
    with selected.open("rb") as source, candidate.open("xb") as target:
        shutil.copyfileobj(source, target, length=1024**2)
    refused = False
    try:
        BackupStore(storage / "store", replace(policy, max_bytes=1)).publish(
            candidate, manifest["files"]
        )
    except ValueError:
        refused = True
    finally:
        candidate.unlink()
    if not refused or store.inspect() != before:
        raise ValueError("Failed attempt modified the verified history")
    result = snapshot(world, storage, policy)
    after = store.inspect()
    if (
        result["retired"] != 1
        or [row["id"] for row in after[:-1]] != [row["id"] for row in before[1:]]
        or len(after) != policy.max_count
    ):
        raise ValueError("Unexpected retention history")
    return {
        "quota_refused_without_history_change": True,
        "new_verified_before_retirement": True,
        "retired": result["retired"],
        "history": after,
    }


if __name__ == "__main__":
    import sys

    if sys.argv[1] == "publish":
        report = snapshot(Path("/server/lab-world"), Path("/backup"), LAB_POLICY)
    elif sys.argv[1] == "finish":
        report = fault_and_retention(
            Path("/server/lab-world"), Path("/backup"), LAB_POLICY
        )
    elif sys.argv[1] == "inspect":
        report = {"snapshots": BackupStore(Path("/backup/store"), LAB_POLICY).inspect()}
    else:
        raise ValueError("Unknown owned storage operation")
    print(json.dumps(report))
