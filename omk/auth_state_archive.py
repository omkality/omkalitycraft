"""Offline Linux helper. Call only after stopping the volume's Drasl process.

Copies the WHOLE state directory, including SQLite WAL/SHM, skins and signing key.
Restore accepts only our manifest format into an empty, isolated target volume.
This does not grant permission to expose the restored service to players.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
from pathlib import Path, PurePosixPath

MAX_BYTES = 128 * 1024**2  # Explicit lab budget, not a production retention policy.
MAX_FILES = 10000


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def inventory(root):
    result = {}
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("Unsupported state entry")
        if path.is_file():
            total += path.stat().st_size
            if total > MAX_BYTES or len(result) >= MAX_FILES:
                raise ValueError("State exceeds archive budget")
            result[path.relative_to(root).as_posix()] = digest(path)
    if "drasl.db" not in result or "key.pkcs8" not in result:
        raise ValueError("Incomplete Drasl state")
    return result


def integrity(root):
    # mode=ro still observes a WAL. It must run in the writable isolated helper
    # mount, as SQLite may need to create shared memory. No active Drasl process.
    with sqlite3.connect((root / "drasl.db").as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")


def snapshot(root, destination):
    if destination.exists():
        raise ValueError("Snapshot already exists")
    integrity(root)
    records = inventory(root)
    temporary = destination.with_suffix(".partial")
    # A failed partial is never advertised as a usable snapshot.
    with temporary.open("xb") as raw:
        os.chmod(temporary, 0o600)
        with tarfile.open(fileobj=raw, mode="w") as tar:
            for name in records:
                tar.add(root / name, arcname=name, recursive=False)
        raw.flush()
        os.fsync(raw.fileno())
    if temporary.stat().st_size > MAX_BYTES + MAX_FILES * 2048:
        raise ValueError("Archive exceeds budget")
    manifest = {
        "schema": 1,
        "sha256": digest(temporary),
        "files": records,
    }
    destination.with_suffix(".json").write_text(json.dumps(manifest), encoding="utf-8")
    os.chmod(destination.with_suffix(".json"), 0o600)
    temporary.rename(destination)
    return {
        "sqlite_integrity": True,
        "files": len(records),
        "sha256": manifest["sha256"],
    }


def restore(root, archive):
    if any(root.iterdir()):
        raise ValueError("Restore requires an empty isolated volume")
    if archive.stat().st_size > MAX_BYTES + MAX_FILES * 2048:
        raise ValueError("Archive exceeds budget")
    raw = archive.with_suffix(".json").read_bytes()
    if len(raw) > 2 * 1024**2:
        raise ValueError("Manifest exceeds budget")
    manifest = json.loads(raw)
    if manifest.get("schema") != 1 or digest(archive) != manifest["sha256"]:
        raise ValueError("Archive digest mismatch")
    records, total = {}, 0
    # Validate every member BEFORE writing anything. Never extractall/untrusted links.
    with tarfile.open(archive, "r:") as tar:
        for item in tar:
            name = PurePosixPath(item.name)
            total += item.size
            if (
                not item.isfile()
                or name.is_absolute()
                or ".." in name.parts
                or "\\" in item.name
                or str(name) != item.name
                or item.name in records
                or total > MAX_BYTES
                or len(records) >= MAX_FILES
            ):
                raise ValueError("Unsafe archive member")
            with tar.extractfile(item) as file:
                records[item.name] = hashlib.file_digest(file, "sha256").hexdigest()
        if (
            records != manifest["files"]
            or not {"drasl.db", "key.pkcs8"} <= records.keys()
        ):
            raise ValueError("State inventory mismatch")
        for item in tar.getmembers():
            path = root / item.name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open("xb") as file:
                os.chmod(path, 0o600)
                with tar.extractfile(item) as source:
                    shutil.copyfileobj(source, file, length=1024 * 1024)
                file.flush()
                os.fsync(file.fileno())
    integrity(root)
    return {
        "sqlite_integrity": True,
        "files": len(records),
        "quarantine_required": True,
    }


if __name__ == "__main__":
    import sys

    print(
        json.dumps(
            {"snapshot": snapshot, "restore": restore}[sys.argv[1]](
                Path("/state"), Path("/backup/state.tar")
            )
        )
    )
