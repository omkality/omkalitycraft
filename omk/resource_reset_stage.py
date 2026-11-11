"""Prepare a data-only candidate in a fresh Linux target; never approve its start.

The source and verified backup are read-only. No source deletion, lifecycle,
runtime deployment or promotion is implemented here. The owner controller binds
this data-only worker to maintenance, a completed backup and a start barrier.
"""

import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

from omk import (
    enderutilities_reset as ender,
    resource_reset_inventory as audit,
    resource_reset_preflight,
    resource_reset_transform as transform,
)
from omk.backup_store import (
    BackupPolicy,
    BackupStore,
    _directory,
    _json_write,
    _sync_directory,
)
from omk.cold_backup_worker import digest, source_summary
from omk.linux_world_restore import _copy, _read
from omk.stopped_world_backup import inventory

PLAN = ".omk-resource-reset-plan.json"
DONE = ".omk-resource-reset-staged.json"


def _request(request):
    keys = {
        "schema",
        "action",
        "operation",
        "world",
        "dimension",
        "position",
        "snapshot",
        "world_max_bytes",
        "policy",
    }
    if isinstance(request, dict) and request.get("action") in {"stage", "verify"}:
        keys.add("expected")
    if isinstance(request, dict) and "preflight_options" in request:
        keys.add("preflight_options")
    if (
        sys.platform != "linux"
        or not isinstance(request, dict)
        or set(request) != keys
        or type(request["schema"]) is not int
        or request["schema"] != 1
        or request["action"] not in {"plan", "stage", "verify"}
        or not isinstance(request["operation"], str)
        or not re.fullmatch(r"[a-f0-9]{32}", request["operation"])
        or not isinstance(request["world"], str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request["world"])
        or not isinstance(request["snapshot"], str)
        or not re.fullmatch(r"snapshot-[a-f0-9]{32}", request["snapshot"])
        or type(request["world_max_bytes"]) is not int
        or not 1 <= request["world_max_bytes"] <= 1024**4
    ):
        raise ValueError("Invalid Linux resource staging request")
    audit.validate_dimension(request["dimension"])
    if request["position"] != "auto":
        transform.landing(request["position"])
    BackupPolicy(**request["policy"])
    if "preflight_options" in request:
        resource_reset_preflight.options_checked(request["preflight_options"])


def _inputs(request, source, storage, target):
    for path in (source, storage, target):
        _directory(path)
        if path.resolve() != path.absolute():
            raise ValueError("Resource staging paths must be regular and absolute")
    if any(
        a.samefile(b) or a.is_relative_to(b) or b.is_relative_to(a)
        for a, b in ((source, storage), (source, target), (storage, target))
    ):
        raise ValueError("Resource staging paths alias")
    if {p.name for p in storage.iterdir()} != {"store"}:
        raise ValueError("Unfinished or foreign backup publication")
    store = BackupStore(
        storage / "store",
        BackupPolicy(**request["policy"]),
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    snapshots = store._snapshots()
    if not snapshots or snapshots[-1][1].name != request["snapshot"]:
        raise ValueError("Resource reset requires the latest verified current backup")
    archive, manifest = store.readonly_snapshot(request["snapshot"])
    files, source_identity = source_summary(source, request)
    if files != manifest["files"]:
        raise ValueError(
            "Fresh verified backup of the entire current world is required"
        )
    inspected = audit.inspect_resource(
        source,
        request["world"],
        request["dimension"],
        world_max_bytes=request["world_max_bytes"],
    )
    position, preflight = request["position"], None
    if position == "auto":
        preflight = resource_reset_preflight.preflight(
            source,
            request["world"],
            request["dimension"],
            options=request.get("preflight_options"),
            world_max_bytes=request["world_max_bytes"],
        )
        if not preflight["can_stage_data"]:
            raise ValueError(
                "Resource auto stage needs reviewed landing; known mod links require "
                "reviewed adapters and opaque records are forbidden"
            )
        position = preflight["landing"]["position"]
    payloads = transform.changes(
        source,
        request["world"],
        request["dimension"],
        position,
        files,
        enderutilities_targets=bool(
            preflight and ender.ADAPTER in preflight.get("adapters", {})
        ),
    )
    result = transform.result_inventory(
        files, payloads, request["world"], request["dimension"]
    )
    after, after_identity = source_summary(source, request)
    if after != files or after_identity != source_identity:
        raise ValueError("Resource source changed while planning edits")
    plan = {
        "schema": 1,
        "operation": request["operation"],
        "world": request["world"],
        "dimension": request["dimension"],
        "position": position,
        "snapshot": request["snapshot"],
        "archive_sha256": manifest["sha256"],
        "source": source_identity,
        "resource_identity": inspected["resource_identity"],
        "result_inventory_sha256": digest(result),
        "retained_files": len(result),
        "omitted_files": len(files) - len(result),
        "edit_sha256": digest(
            {
                name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in payloads.items()
            }
        ),
        "changed_files": len(payloads),
        "references_before": inspected["references"],
        "settings_sha256": digest(
            {k: request[k] for k in ("world_max_bytes", "policy")}
        ),
        "ready_for_start": False,
        "landing_verified": False,
        "portal_adapters_reviewed": False,
    }
    if preflight is not None:
        plan["preflight"] = preflight
        plan["landing_geometry_verified"] = True
    return archive, manifest, payloads, result, plan


def _fresh(target):
    if any(target.iterdir()):
        raise ValueError(
            "Resource reset requires an empty target; never repeat a partial stage"
        )


def _space(request, target, result):
    required = (
        sum(v["bytes"] for v in result.values()) + 4096 * len(result) + 4 * 1024**2
    )
    if (
        required > request["policy"]["staging_bytes"]
        or shutil.disk_usage(target).free
        < required + request["policy"]["reserve_bytes"]
    ):
        raise OSError("Resource staging budget or free-space reserve would be violated")


def _write_edit(target, name, data):
    path = target / name
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("xb") as output:
        path.chmod(0o600)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    parent = path.parent
    while parent.is_relative_to(target):
        _sync_directory(parent)
        if parent == target:
            break
        parent = parent.parent


def _verified(request, source, storage, target):
    _archive, _manifest, _payloads, result, plan = _inputs(
        request, source, storage, target
    )
    if plan != request["expected"] or _read(target / PLAN) != plan:
        raise ValueError("Resource source, backup or recorded plan changed")
    if {p.name for p in target.iterdir()} - {request["world"], PLAN, DONE}:
        raise ValueError("Foreign files in resource staging target")
    actual = inventory(
        target / request["world"],
        world_name=request["world"],
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    if (
        actual != result
        or (target / request["world"] / f"DIM{request['dimension']}").exists()
    ):
        raise ValueError("Resource candidate differs from expected retained files")
    return {
        "operation": request["operation"],
        "plan_sha256": digest(plan),
        "world_inventory_sha256": digest(actual),
        "staged": True,
        "promoted": False,
        "ready_for_start": False,
        "landing_verified": False,
        "portal_adapters_reviewed": False,
    }


def execute(
    request, source=Path("/server"), storage=Path("/backup"), target=Path("/target")
):
    _request(request)
    if request["action"] == "verify":
        result = _verified(request, source, storage, target)
        if _read(target / DONE) != result:
            raise ValueError("Resource candidate has no complete receipt")
        return result
    _directory(target)
    _fresh(target)
    archive, manifest, payloads, result, plan = _inputs(
        request, source, storage, target
    )
    _space(request, target, result)
    if request["action"] == "plan":
        return plan
    if plan != request["expected"]:
        raise ValueError("Resource staging input changed after plan")
    _json_write(target / PLAN, plan)
    _sync_directory(target)
    (target / request["world"]).mkdir(mode=0o700)
    with zipfile.ZipFile(archive) as original:
        for name in sorted(result):
            if name in payloads:
                _write_edit(target, name, payloads[name])
            else:
                _copy(original, name, target, manifest["files"][name])
    verified = _verified(request, source, storage, target)
    _json_write(target / DONE, verified)
    _sync_directory(target)
    return verified


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("Resource staging request exceeds limit")
        print(json.dumps({"ok": True, "result": execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
