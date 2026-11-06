"""Linux worker for staged cold backups. Invoked by the local owner controller.

No Docker socket/network, credentials or lifecycle commands inside this worker.
The controller verifies stopped-container identity before and after preparation.
"""

import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

from omk.backup_archive import MAX_MANIFEST_BYTES, regular_file, verify_archive
from omk.backup_store import BackupPolicy, BackupStore, _json_write, _sync_directory
from omk.stopped_world_backup import inventory


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def runtime_files(root):
    records, total = {}, 0
    paths = [*root.glob("*.jar"), root / "server.properties"]
    for folder in (
        "mods",
        "libraries",
        "config",
        "scripts",
        "groovy",
        "resources",
        "local",
    ):
        base = root / folder
        if base.is_symlink():
            raise ValueError("Linked runtime directory")
        if not base.exists():
            continue
        for directory, folders, files in os.walk(base, followlinks=False):
            if any((Path(directory) / name).is_symlink() for name in folders):
                raise ValueError("Linked runtime entry")
            paths.extend(Path(directory) / name for name in files)
    for name in ("authlib-injector.jar", "log4j2.xml"):
        if (root / ".omk" / name).exists():
            paths.append(root / ".omk" / name)
    for path in paths:
        length = regular_file(path)
        total += length
        if len(records) >= 20000 or total > 8 * 1024**3:
            raise ValueError("Runtime fingerprint exceeds reviewed limit")
        with path.open("rb") as file:
            records[path.relative_to(root).as_posix()] = hashlib.file_digest(
                file, "sha256"
            ).hexdigest()
    return records


def runtime_digest(root):
    return digest(runtime_files(root))


def source_summary(root, request):
    files = inventory(
        root / request["world"],
        world_name=request["world"],
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    return files, {
        "inventory_sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True).encode()
        ).hexdigest(),
        "files": len(files),
        "expanded_bytes": sum(row["bytes"] for row in files.values()),
        "runtime_sha256": runtime_digest(root),
    }


def store_for(storage, request, *, create=False):
    allowed = {"store", "incoming.zip", "prepared.json", "receipt.json"}
    if any(path.name not in allowed or path.is_symlink() for path in storage.iterdir()):
        raise ValueError("Foreign files in backup volume")
    policy = BackupPolicy(**request["policy"])
    kwargs = {
        "max_expanded_bytes": request["world_max_bytes"],
        "path_policy": "linux-server",
    }
    root = storage / "store"
    if not root.exists() and create:
        return BackupStore.create(root, policy, **kwargs)
    return BackupStore(root, policy, **kwargs) if root.exists() else None


def inspect_store(storage, request):
    store = store_for(storage, request)
    if any(
        (storage / file).exists()
        for file in ("incoming.zip", "prepared.json", "receipt.json")
    ):
        raise ValueError("Unfinished operation requires owner inspection")
    return [] if store is None else store.inspect()


def prepare(root, storage, request):
    import shutil  # noqa: PLC0415

    before = inspect_store(storage, request)
    files, summary = source_summary(root, request)
    if summary != request["source"] or before != request["history"]:
        raise ValueError("Source or retained history changed after plan")
    overhead = 2 * MAX_MANIFEST_BYTES + len(files) * 2048
    required = summary["expanded_bytes"] + overhead
    policy = BackupPolicy(**request["policy"])
    if (
        required > policy.staging_bytes
        or shutil.disk_usage(storage).free < required * 2 + policy.reserve_bytes
    ):
        raise OSError("Insufficient staging or free reserve")
    store_for(storage, request, create=True)
    with (storage / "incoming.zip").open("xb") as file:
        os.chmod(storage / "incoming.zip", 0o600)
        with zipfile.ZipFile(
            file, "w", zipfile.ZIP_DEFLATED, compresslevel=1
        ) as archive:
            for name in sorted(files):
                archive.write(root / name, name)
        file.flush()
        os.fsync(file.fileno())
    if source_summary(root, request)[1] != summary:
        raise ValueError("Stopped source changed during preparation")
    sha = verify_archive(
        storage / "incoming.zip",
        files,
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    _json_write(
        storage / "prepared.json",
        {
            "operation": request["operation"],
            "sha256": sha,
            "files": files,
            "source": summary,
        },
    )
    os.chmod(storage / "prepared.json", 0o600)
    _sync_directory(storage)
    return {"prepared": True, "sha256": sha, **summary}


def publish(storage, request):
    from omk.backup_store import _json_read  # noqa: PLC0415

    prepared = _json_read(storage / "prepared.json")
    if (
        prepared["operation"] != request["operation"]
        or prepared["source"] != request["source"]
    ):
        raise ValueError("Prepared operation binding mismatch")
    verify_archive(
        storage / "incoming.zip",
        prepared["files"],
        prepared["sha256"],
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    store = store_for(storage, request)
    if store.inspect() != request["history"]:
        raise ValueError("History changed before publication")
    result = store.publish(storage / "incoming.zip", prepared["files"])
    # An uncertain controller must not repeat a successful rotation. Receipt is
    # retained until its durable journal acknowledges it; the next plan refuses it.
    _json_write(
        storage / "receipt.json", {"operation": request["operation"], "result": result}
    )
    _sync_directory(storage)
    return result


def acknowledge(storage, request):
    from omk.backup_store import _json_read  # noqa: PLC0415

    recovered = recover(storage, request)
    if recovered != request["result"]:
        raise ValueError("Published result mismatch")
    receipt = storage / "receipt.json"
    if receipt.exists() and _json_read(receipt) != {
        "operation": request["operation"],
        "result": request["result"],
    }:
        raise ValueError("Receipt mismatch")
    manifest = _json_read(storage / "store" / recovered["id"] / "manifest.json")
    if (storage / "incoming.zip").exists():
        verify_archive(
            storage / "incoming.zip",
            manifest["files"],
            recovered["sha256"],
            max_expanded_bytes=request["world_max_bytes"],
            path_policy="linux-server",
        )
    if (storage / "prepared.json").exists():
        prepared = _json_read(storage / "prepared.json")
        if (
            prepared["operation"] != request["operation"]
            or prepared["sha256"] != recovered["sha256"]
        ):
            raise ValueError("Prepared receipt mismatch")
    for name in ("incoming.zip", "prepared.json", "receipt.json"):
        if (storage / name).exists():
            regular_file(storage / name)
    for name in ("incoming.zip", "prepared.json", "receipt.json"):
        (storage / name).unlink(missing_ok=True)
    _sync_directory(storage)
    return {"acknowledged": True}


def recover(storage, request):
    from omk.backup_store import _json_read  # noqa: PLC0415

    store = store_for(storage, request)
    history = store.inspect()
    sequence = max((row["sequence"] for row in request["history"]), default=0) + 1
    matches = [row for row in history if row["sequence"] == sequence]
    if len(matches) != 1 or any(row["sequence"] > sequence for row in history):
        raise ValueError("No unambiguous committed snapshot")
    selected = matches[0]
    manifest = _json_read(storage / "store" / selected["id"] / "manifest.json")
    if manifest["sha256"] != request["prepared"]["sha256"]:
        raise ValueError("Published archive differs from prepared operation")
    old = {row["id"] for row in request["history"]}
    current = {row["id"] for row in history}
    if current - old != {selected["id"]}:
        raise ValueError("Unexpected retained history")
    return {
        "id": selected["id"],
        "sequence": sequence,
        "sha256": manifest["sha256"],
        "verified": True,
        "retired": len(old - current),
    }


def execute(request, root=Path("/server"), storage=Path("/backup")):
    action = request["action"]
    if action == "inspect":
        return {"history": inspect_store(storage, request)}
    if action == "plan":
        return {
            "source": source_summary(root, request)[1],
            "history": inspect_store(storage, request),
        }
    if action == "prepare":
        return prepare(root, storage, request)
    if action == "publish":
        return publish(storage, request)
    if action == "acknowledge":
        return acknowledge(storage, request)
    if action == "recover":
        return recover(storage, request)
    if action == "cancel":
        return cancel(storage, request)
    if action == "list":
        store = store_for(storage, request)
        return {
            "history": [] if store is None else store.inspect(),
            "pending": any(
                (storage / file).exists()
                for file in ("incoming.zip", "prepared.json", "receipt.json")
            ),
        }
    raise ValueError("Unknown cold backup action")


def cancel(storage, request):
    from omk.backup_store import _json_read  # noqa: PLC0415

    store = store_for(storage, request)
    history = [] if store is None else store.inspect()
    if history != request["history"] or (storage / "receipt.json").exists():
        raise ValueError("Publication may exist; reconcile instead of cancelling")
    prepared = storage / "prepared.json"
    if (
        prepared.exists()
        and _json_read(prepared).get("operation") != request["operation"]
    ):
        raise ValueError("Staging belongs to another operation")
    for name in ("incoming.zip", "prepared.json"):
        if (storage / name).exists():
            regular_file(storage / name)
    for name in ("incoming.zip", "prepared.json"):
        (storage / name).unlink(missing_ok=True)
    _sync_directory(storage)
    return {"cancelled": True, "previous_history_unchanged": True}


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("Worker request too large")
        print(json.dumps({"ok": True, **execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
