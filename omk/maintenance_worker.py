"""Readonly runtime / current backup proof, without Docker socket or credentials."""

import hashlib
import json
import os
import sys
from pathlib import Path

from omk.backup_archive import regular_file
from omk.backup_store import _json_read
from omk.cold_backup_worker import runtime_digest, source_summary, store_for
from omk.fs import regular


def no_operators(root):
    """Read an existing zero-entry list without changing the server's access files."""
    path = root / "ops.json"

    def signature(info):
        return (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_nlink,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )

    def identity():
        if not regular(path, root):
            raise ValueError("Operator list must be an ordinary file")
        info = path.stat()
        if info.st_nlink != 1 or info.st_size > 65536:
            raise ValueError("Invalid operator list file")
        return signature(info)

    before = identity()
    with path.open("rb") as stream:
        if signature(os.fstat(stream.fileno())) != before:
            raise ValueError("Operator list changed before reading")
        raw = stream.read(65537)
        if len(raw) > 65536 or signature(os.fstat(stream.fileno())) != before:
            raise ValueError("Operator list changed while reading")
    if identity() != before:
        raise ValueError("Operator list changed after reading")
    if json.loads(raw.decode("utf-8")) != []:
        raise ValueError("Operator list must be an empty array")
    return {"operators_sha256": hashlib.sha256(raw).hexdigest(), "operator_count": 0}


def execute(request, root=Path("/server"), storage=Path("/backup")):
    if request["action"] == "operators":
        return no_operators(root)
    if request["action"] == "nightly-policy":
        from omk.ftb_backup_policy import inspect  # noqa: PLC0415

        return inspect(root)
    if request["action"] == "runtime":
        path = root / "server.properties"
        if regular_file(path) > 65536:
            raise ValueError("Oversized server properties")
        # Only canonical generated keys are admitted; never emit the password.
        lines = path.read_text(encoding="utf-8").splitlines()
        values = {}
        for key in ("enable-rcon", "rcon.port"):
            found = [s for s in lines if s.startswith(key + "=")]
            if len(found) != 1:
                raise ValueError("Missing or duplicate RCON property")
            values[key] = found[0].split("=", 1)[1]
        if values != {
            "enable-rcon": "true",
            "rcon.port": str(request["rcon_container_port"]),
        }:
            raise ValueError("RCON properties do not match the explicit binding")
        before = runtime_digest(root)
        if runtime_digest(root) != before:
            raise ValueError("Runtime changed while being inspected")
        return {"runtime_sha256": before}
    if request["action"] != "proof":
        raise ValueError("Unknown maintenance worker action")
    # No store lock/write: mounts are readonly and controller holds backups.lock.
    if any(p.name != "store" for p in storage.iterdir()):
        raise ValueError("Backup has unfinished or foreign staging")
    store = store_for(storage, request)
    rows = [] if store is None else store._snapshots()
    if not rows or rows[-1][1].name != request["snapshot"]["id"]:
        raise ValueError("Completed backup is no longer the latest snapshot")
    manifest = _json_read(rows[-1][1] / "manifest.json")
    files, source = source_summary(root, request)
    if (
        manifest["sha256"] != request["snapshot"]["sha256"]
        or manifest["files"] != files
        or source != request["source"]
    ):
        raise ValueError("Backup does not match the stopped current source")
    return {"source": source, "snapshot": request["snapshot"]}


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("Maintenance request too large")
        print(json.dumps({"ok": True, **execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
