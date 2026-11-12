"""Readonly runtime / current backup proof, without Docker socket or credentials."""

import json
import sys
from pathlib import Path

from omk.backup_archive import regular_file
from omk.backup_store import _json_read
from omk.cold_backup_worker import runtime_digest, source_summary, store_for


def execute(request, root=Path("/server"), storage=Path("/backup")):
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
