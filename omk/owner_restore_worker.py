"""Owner restore data worker: readonly source/store, a fresh stopped target only.

No Docker socket, lifecycle, promotion, deletion or retry. JSON contains hashes,
not passwords or source properties. A complete stage may be verified after a
controller interruption; a partial stage always requires owner investigation.
"""

import json
import re
import shutil
import sys
from pathlib import Path

from omk import (
    linux_restore_policy as policy,
    linux_world_restore as raw,
)
from omk.backup_store import (
    BackupPolicy,
    BackupStore,
    _directory,
    _json_read,
    _sync_directory,
)
from omk.cold_backup_worker import digest, runtime_files, source_summary

PLAN = ".omk-owner-restore-plan.json"
DONE = ".omk-owner-restore-staged.json"
MUTABLE_RUNTIME = {"server.properties", policy.RANKS}


class CurrentBackupRequired(ValueError):
    """The current world has no matching latest verified checkpoint."""


class RuntimeArtifactsMismatch(ValueError):
    """Prepared target JARs differ from the stopped current runtime."""


def _runtime(root):
    files = runtime_files(root)
    return {
        "full": digest(files),
        "immutable": digest(
            {k: v for k, v in files.items() if k not in MUTABLE_RUNTIME}
        ),
        "artifacts": digest({k: v for k, v in files.items() if k.endswith(".jar")}),
    }


def _inputs(request, storage, target, current):
    identity = raw._request(request, target)
    _directory(current)
    if current.samefile(target) or not re.fullmatch(
        r"snapshot-[a-f0-9]{32}", request.get("snapshot", "")
    ):
        raise ValueError("Invalid owner restore sources")
    _directory(storage)
    if storage.samefile(target) or storage.samefile(current):
        raise ValueError("Owner restore sources alias")
    if any(p.name != "store" for p in storage.iterdir()):
        raise ValueError("Backup publication is unfinished or has foreign files")
    store = BackupStore(
        storage / "store",
        BackupPolicy(**request["policy"]),
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    snapshots = store._snapshots()
    if not snapshots:
        raise ValueError("No published backup")
    selected = next(
        (path for _, path, _ in snapshots if path.name == request["snapshot"]), None
    )
    if selected is None:
        raise ValueError("Selected backup is not retained")
    manifest = _json_read(selected / "manifest.json")
    latest = snapshots[-1][1]
    latest_manifest = _json_read(latest / "manifest.json")
    files, current_world = source_summary(current, request)
    if files != latest_manifest["files"]:
        raise CurrentBackupRequired(
            "Make a fresh verified current-world backup before restoring"
        )
    # Read and reconcile before any target write, including unknown-field refusal.
    policy.ftb.check_runtime(current)
    policy.ftb.check_runtime(target)
    historical = policy.ftb.read_zip(
        selected / "archive.zip",
        world_name=request["world"],
        path_policy="linux-server",
        max_expanded_bytes=request["world_max_bytes"],
    )
    _, current_ftb, current_policy = policy._current(current, request["world"])
    policy.reconcile.merged_records(current_ftb, historical)
    runtime = _runtime(target)
    if runtime["artifacts"] != _runtime(current)["artifacts"]:
        raise RuntimeArtifactsMismatch(
            "Source and target runtime JAR inventories differ"
        )
    return {
        **identity,
        "snapshot": request["snapshot"],
        "archive_sha256": manifest["sha256"],
        "historical_files": len(manifest["files"]),
        "historical_bytes": sum(v["bytes"] for v in manifest["files"].values()),
        "current_snapshot": latest.name,
        "current_archive_sha256": latest_manifest["sha256"],
        "current_world": current_world,
        "current_policy": current_policy,
        "target_runtime": runtime,
    }


def _fresh(target, world):
    if any(
        (target / name).exists() or (target / name).is_symlink()
        for name in (
            world,
            PLAN,
            DONE,
            raw.OWNER,
            raw.PLAN,
            raw.DONE,
            *raw.POLICY_MARKERS,
            policy.STAGING,
        )
    ):
        raise ValueError("Owner restore requires a fresh target; never repeat apply")


def plan(request, storage, target, current):
    _fresh(target, request["world"])
    expected = _inputs(request, storage, target, current)
    required = (
        expected["historical_bytes"] + 4096 * expected["historical_files"] + 4 * 1024**2
    )
    if required > request["policy"]["staging_bytes"] or (
        shutil.disk_usage(target).free < required + request["policy"]["reserve_bytes"]
    ):
        raise OSError("Restore staging budget or free-space reserve would be violated")
    return expected


def _request(request):
    return {**request, "archive_sha256": request["expected"]["archive_sha256"]}


def apply(request, storage, target, current):
    if plan(request, storage, target, current) != request["expected"]:
        raise ValueError("Restore input changed after planning")
    policy._write_record(target / PLAN, request["expected"])
    value = _request(request)
    for action in ("initialize", "stage"):
        raw.execute({**value, "action": action}, storage / "store", target)
    if _runtime(target) != request["expected"]["target_runtime"]:
        raise ValueError("Target runtime changed during historical extraction")
    policy.execute(
        {**value, "action": "stage-policy"}, storage / "store", target, current
    )
    result = _verified_data(request, storage, target, current)
    policy._write_record(target / DONE, result)
    _sync_directory(target)
    return result


def _verified_data(request, storage, target, current):
    expected = request["expected"]
    if raw._read(target / PLAN) != expected:
        raise ValueError("Owner restore plan differs")
    actual = _inputs(request, storage, target, current)
    # Only the current whitelist flag and ranks may alter target runtime during stage.
    actual["target_runtime"]["full"] = expected["target_runtime"]["full"]
    if actual != expected:
        raise ValueError("Current source, store or target runtime changed")
    result = policy.execute(
        {**_request(request), "action": "verify-policy"},
        storage / "store",
        target,
        current,
    )
    return {
        "operation": request["operation"],
        "plan_sha256": policy.digest((target / PLAN).read_bytes()),
        "world_inventory_sha256": result["world_inventory_sha256"],
        "snapshot": expected["snapshot"],
        "archive_sha256": expected["archive_sha256"],
        "current_snapshot": expected["current_snapshot"],
        "staged": True,
        "promoted": False,
    }


def verify(request, storage, target, current):
    result = _verified_data(request, storage, target, current)
    if raw._read(target / DONE) != result:
        raise ValueError(
            "Owner restore has no complete receipt; inspect partial target"
        )
    return result


def execute(
    request, storage=Path("/backup"), target=Path("/restore"), current=Path("/current")
):
    if sys.platform != "linux":
        raise ValueError("Owner world restore requires Linux")
    functions = {"plan": plan, "apply": apply, "verify": verify}
    if request.get("action") not in functions:
        raise ValueError("Unknown owner restore action")
    return functions[request["action"]](request, storage, target, current)


if __name__ == "__main__":
    try:
        data = sys.stdin.buffer.read(65537)
        if len(data) > 65536:
            raise ValueError("Owner restore request exceeds limit")
        print(json.dumps({"ok": True, "result": execute(json.loads(data))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
