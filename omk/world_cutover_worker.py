"""Cold same-volume world exchange, retaining both generations. No lifecycle API."""

import json
import os
import re
import shutil
import sys
from pathlib import Path

from omk import resource_reset_runtime as runtime
from omk.backup_store import (
    BackupPolicy,
    BackupStore,
    _directory,
    _json_write,
    _sync_directory,
)
from omk.cold_backup_worker import digest
from omk.linux_world_restore import _read
from omk.stopped_world_backup import inventory

ROOT = ".omk-cutovers"
CONTROL = Path("/control")
ADAPTER = "forge112-cold-world-exchange-v1"
ACTIONS = {"plan", "apply", "verify", "recover", "revert", "verify-revert", "cancel"}


def request_checked(request):
    if (
        not isinstance(request, dict)
        or set(request)
        != {"schema", "action", "operation", "runtime", "expected", "write_lease"}
        or type(request["schema"]) is not int
        or request["schema"] != 1
        or request["action"] not in ACTIONS
        or not isinstance(request["operation"], str)
        or not re.fullmatch(r"[a-f0-9]{32}", request["operation"])
    ):
        raise ValueError("Invalid cold world exchange request")
    runtime._request(request["runtime"])
    if request["runtime"]["action"] != "runtime-verify":
        raise ValueError("Exchange requires a sealed runtime candidate")
    if (request["expected"] is None) != (request["action"] == "plan"):
        raise ValueError("Exchange requires a frozen identity")
    nonce = request["write_lease"]
    if nonce is not None and (
        not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32}", nonce)
    ):
        raise ValueError("Invalid world write lease")


def lease(request, *, writing=False):
    value = _read(CONTROL / "lease.json")
    if (
        set(value) != {"schema", "operation", "stage", "write_lease"}
        or type(value["schema"]) is not int
        or value["schema"] != 1
        or value["operation"] != request["operation"]
    ):
        raise ValueError("World write lease identity differs")
    expected, actual = request["write_lease"], value["write_lease"]
    if writing:
        stage = "reverting" if request["action"] == "revert" else "applying"
        if expected is None or actual != expected or value["stage"] != stage:
            raise ValueError("World write lease revoked or replaced")
    elif actual is not None and actual != expected:
        raise ValueError("World write lease is not closed or has another attempt")


def tree(root, data):
    return inventory(
        root / data["world"],
        world_name=data["world"],
        max_expanded_bytes=data["world_max_bytes"],
        path_policy="linux-server",
    )


def backup(storage, data):
    if {p.name for p in storage.iterdir()} != {"store"}:
        raise ValueError("Unfinished backup publication")
    store = BackupStore(
        storage / "store",
        BackupPolicy(**data["policy"]),
        max_expanded_bytes=data["world_max_bytes"],
        path_policy="linux-server",
    )
    snapshots = store._snapshots()
    if not snapshots or snapshots[-1][1].name != data["snapshot"]:
        raise ValueError("Exchange requires its unchanged latest backup")
    _archive, manifest = store.readonly_snapshot(data["snapshot"])
    if manifest["sha256"] != data["expected"]["archive_sha256"]:
        raise ValueError("Exchange backup hash changed")
    return manifest["files"]


def inputs(request, source, storage, target):
    for root in (source, storage, target):
        _directory(root)
        if root.resolve() != root.absolute():
            raise ValueError("Exchange roots must be ordinary absolute paths")
    if os.name == "posix" and source.stat().st_uid != os.geteuid():
        raise ValueError("Source volume root must be owned by the reviewed worker UID")
    if any(
        a.samefile(b) or a.is_relative_to(b) or b.is_relative_to(a)
        for a, b in ((source, storage), (source, target), (storage, target))
    ):
        raise ValueError("Exchange roots alias")
    data = request["runtime"]
    original = backup(storage, data)
    manifest = runtime.files(source, data["world"])
    runtime._layout(target, data["world"], manifest, complete=True)
    candidate = tree(target, data)
    expected_runtime = data["runtime_expected"]
    receipt = _read(target / runtime.DONE)
    if (
        digest(candidate) != expected_runtime["world_inventory_sha256"]
        or digest(manifest) != expected_runtime["runtime_inventory_sha256"]
        or receipt.get("runtime_plan_sha256") != digest(expected_runtime)
        or receipt.get("world_inventory_sha256") != digest(candidate)
        or receipt.get("runtime_inventory_sha256") != digest(manifest)
    ):
        raise ValueError("Exchange candidate or current runtime changed")
    identity = {
        "schema": 1,
        "adapter": ADAPTER,
        "operation": request["operation"],
        "resource_operation": data["operation"],
        "world": data["world"],
        "dimension": data["dimension"],
        "snapshot": data["snapshot"],
        "archive_sha256": data["expected"]["archive_sha256"],
        "source_inventory_sha256": digest(original),
        "candidate_inventory_sha256": digest(candidate),
        "runtime_inventory_sha256": digest(manifest),
        "runtime_receipt_sha256": digest(receipt),
        "request_sha256": digest(data),
        "source_files": len(original),
        "candidate_files": len(candidate),
        "source_bytes": sum(v["bytes"] for v in original.values()),
        "candidate_bytes": sum(v["bytes"] for v in candidate.values()),
    }
    if request["expected"] is not None and identity != request["expected"]:
        raise ValueError("Exchange identity differs from its plan")
    return original, candidate, identity


def history_bytes(source):
    root = source / ROOT
    if not root.exists():
        return 0
    _directory(root)
    if len(list(root.iterdir())) > 128:
        raise ValueError("Archive retained cutover history before another exchange")
    total, count = 0, 0
    for directory, folders, names in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in folders:
            _directory(base / name)
        for name in names:
            p = base / name
            if not runtime.regular(p, root) or p.stat().st_nlink != 1:
                raise ValueError("Retained cutover history contains linked files")
            total += p.stat().st_size + 4096
            count += 1
            if count > 500000 or total > 1024**4:
                raise ValueError("Retained exchange history exceeds bound")
    return total


def space(request, source, identity):
    policy = request["runtime"]["policy"]
    retained_root = source / ROOT
    if retained_root.exists() and len(list(retained_root.iterdir())) >= 128:
        raise ValueError("Archive retained generations before another world exchange")
    new_cost = (
        identity["candidate_bytes"] + identity["candidate_files"] * 4096 + 4 * 1024**2
    )
    retained = identity["source_bytes"] + identity["source_files"] * 4096
    # Include the sealed target, the new source copy and the retained old world.
    candidate = request["runtime"]["runtime_expected"]
    total = history_bytes(source) + retained + 2 * new_cost + candidate["runtime_bytes"]
    if (
        total > policy["staging_bytes"]
        or shutil.disk_usage(source).free < new_cost + policy["reserve_bytes"]
    ):
        raise OSError(
            "World exchange staging budget or free-space reserve would be violated"
        )


def paths(source, operation):
    root = source / ROOT / operation
    _directory(source)
    for p in (source / ROOT, root):
        if p.exists() or p.is_symlink():
            _directory(p)
    return root


def owned(root, identity):
    _directory(root)
    if _read(root / "identity.json") != identity:
        raise ValueError("World exchange directory has another identity")
    if {p.name for p in root.iterdir()} - {
        "identity.json",
        "next",
        "previous",
        "rejected",
    }:
        raise ValueError("Foreign world exchange entries")
    for name in ("next", "previous", "rejected"):
        p = root / name
        _directory(p)
        if {v.name for v in p.iterdir()} - {identity["world"]}:
            raise ValueError("Foreign generation in exchange directory")


def state(source, root, data, original, candidate):
    name = data["world"]
    active = tree(source, data) if (source / name).exists() else None
    found = {}
    for key in ("next", "previous", "rejected"):
        base = root / key
        found[key] = tree(base, data) if (base / name).exists() else None
    if active == original and found == {
        "next": candidate,
        "previous": None,
        "rejected": None,
    }:
        return "prepared"
    if active is None and found == {
        "next": candidate,
        "previous": original,
        "rejected": None,
    }:
        return "parked"
    if active == candidate and found == {
        "next": None,
        "previous": original,
        "rejected": None,
    }:
        return "installed"
    if active is None and found == {
        "next": None,
        "previous": original,
        "rejected": candidate,
    }:
        return "reverting"
    if active == original and found == {
        "next": None,
        "previous": None,
        "rejected": candidate,
    }:
        return "reverted"
    raise ValueError("World exchange is partial, changed or has an ambiguous layout")


def move(source, destination):
    if destination.exists() or destination.is_symlink() or source.is_symlink():
        raise ValueError("World rename must not overwrite or follow a link")
    os.rename(source, destination)
    _sync_directory(source.parent)
    _sync_directory(destination.parent)


def swap(source, root, data, phase, request, *, reverting=False):
    name = data["world"]
    if reverting:
        if phase == "installed":
            lease(request, writing=True)
            move(source / name, root / "rejected" / name)
            phase = "reverting"
        if phase == "reverting":
            lease(request, writing=True)
            move(root / "previous" / name, source / name)
    else:
        if phase == "prepared":
            lease(request, writing=True)
            move(source / name, root / "previous" / name)
            phase = "parked"
        if phase == "parked":
            lease(request, writing=True)
            move(root / "next" / name, source / name)


def result(identity, phase):
    return {
        "phase": phase,
        "identity_sha256": digest(identity),
        "old_world_retained": phase != "reverted",
        "ready_for_players": False,
        "server_started": False,
    }


def prepare(request, source, storage, target, root, identity, original, candidate):
    data = request["runtime"]
    if root.exists():
        raise ValueError("World exchange was already attempted; never repeat the copy")
    if tree(source, data) != original:
        raise ValueError("Source world changed before exchange")
    runtime.execute(data, source, storage, target)
    space(request, source, identity)
    lease(request, writing=True)
    root.mkdir(parents=True, mode=0o700)
    for name in ("next", "previous", "rejected"):
        (root / name).mkdir(mode=0o700)
        _sync_directory(root / name)
    _json_write(root / "identity.json", identity)
    _sync_directory(root)
    _sync_directory(root.parent)
    _sync_directory(root.parent.parent)
    for name, entry in sorted(candidate.items()):
        lease(request, writing=True)
        runtime._copy(target, root / "next", name, entry)


def cancel(source, root, data, original, identity):
    if tree(source, data) != original:
        raise ValueError("Cancellation requires the original untouched world")
    if root.exists():
        _directory(root)
        if {p.name for p in root.iterdir()} - {
            "identity.json",
            "next",
            "previous",
            "rejected",
        }:
            raise ValueError("Unknown partial exchange entries")
        for key in ("previous", "rejected"):
            base = root / key
            if base.exists():
                _directory(base)
                if list(base.iterdir()):
                    raise ValueError(
                        "A world rename has occurred; cancellation is forbidden"
                    )
        history_bytes(source)
    if shutil.disk_usage(source).free < data["policy"]["reserve_bytes"]:
        raise OSError("Free disk reserve must be restored before cancelling")
    return result(identity, "cancelled")


def execute(
    request, source=Path("/server"), storage=Path("/backup"), target=Path("/target")
):
    request_checked(request)
    data, action = request["runtime"], request["action"]
    lease(request, writing=action in {"apply", "recover", "revert"})
    original, candidate, identity = inputs(request, source, storage, target)
    root = paths(source, request["operation"])
    if action == "plan":
        if root.exists():
            raise ValueError("World exchange name was already used")
        runtime.execute(data, source, storage, target)
        space(request, source, identity)
        return identity
    if action == "apply":
        prepare(request, source, storage, target, root, identity, original, candidate)
    if action == "cancel":
        return cancel(source, root, data, original, identity)
    owned(root, identity)
    phase = state(source, root, data, original, candidate)
    if action in {"apply", "recover"}:
        if phase not in {"prepared", "parked", "installed"}:
            raise ValueError("Cannot install a reverted generation")
        swap(source, root, data, phase, request)
    elif action == "revert":
        if phase not in {"installed", "reverting", "reverted"}:
            raise ValueError("Only a verified installed generation can be reverted")
        swap(source, root, data, phase, request, reverting=True)
    phase = state(source, root, data, original, candidate)
    lease(request)
    return result(identity, phase)


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("World exchange request exceeds bound")
        print(json.dumps({"ok": True, "result": execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
