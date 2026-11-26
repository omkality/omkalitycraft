"""Prepare a data-only candidate in a fresh Linux target; never approve its start.

The source and verified backup are read-only. No source deletion, lifecycle,
runtime deployment or promotion is implemented here. The owner controller binds
this data-only worker to maintenance, a completed backup and a start barrier.
"""

import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

from omk.backups.backup_store import (
    BackupPolicy,
    BackupStore,
    _directory,
    _json_write,
    _sync_directory,
)
from omk.backups.cold_backup_worker import digest, source_summary
from omk.backups.stopped_world_backup import inventory
from omk.worlds import enderutilities_reset as ender
from omk.worlds.linux_restore_policy import _read as _runtime_file
from omk.worlds.linux_world_restore import _copy, _read, _write_edit
from omk.worlds.reset import (
    dimension_reset,
    resource_reset_inventory as audit,
    resource_reset_preflight,
    resource_reset_transform as transform,
)

PLAN = ".omk-resource-reset-plan.json"
DONE = ".omk-resource-reset-staged.json"


class PreflightRefused(ValueError):
    """Report a known reason that prevents preparing a world reset."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


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
    if isinstance(request, dict) and "reset" in request:
        keys.add("reset")
    if isinstance(request, dict) and "reroll_seed" in request:
        keys.add("reroll_seed")
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
        or (
            "reroll_seed" in request
            and (request["reroll_seed"] is not True or request["dimension"] == 0)
        )
        or not 1 <= request["world_max_bytes"] <= 1024**4
    ):
        raise ValueError("Invalid Linux resource staging request")
    if "reset" not in request:
        audit.validate_dimension(request["dimension"])
    else:
        reset = request["reset"]
        dimension_reset.validate_layout(request["dimension"], reset, allow_full=True)
        if request["position"] != "auto" or (
            "rftools_identity" in reset and request.get("reroll_seed") is not True
        ):
            raise ValueError("Invalid dimension reset request")
    if request["position"] != "auto":
        transform.landing(request["position"])
    BackupPolicy(**request["policy"])
    if "preflight_options" in request:
        resource_reset_preflight.options_checked(request["preflight_options"])


def _changes(request, source, files):
    reset = request.get("reset")
    all_worlds = bool(reset and reset.get("all_worlds"))
    if all_worlds:
        if f"{request['world']}/level.dat" not in files:
            raise ValueError("Full reset requires the verified saved world metadata")
        if reset.get("fresh_world"):
            properties = _runtime_file(source, "server.properties", limit=65536)
            if re.findall(
                rb"^level-seed[ \t]*=[ \t]*([^\r\n]*)\r?$", properties, re.M
            ) != [b""]:
                raise ValueError(
                    "Full reset requires an empty level-seed in server.properties"
                )
        return (
            request["position"],
            None,
            {},
            {"resource_identity": reset, "references": {}},
        )
    inspected = audit.inspect_resource(
        source,
        request["world"],
        request["dimension"],
        world_max_bytes=request["world_max_bytes"],
        reset=reset,
    )
    position, preflight = request["position"], None
    if position == "auto":
        preflight = resource_reset_preflight.preflight(
            source,
            request["world"],
            request["dimension"],
            options=request.get("preflight_options"),
            world_max_bytes=request["world_max_bytes"],
            **({"reset": request["reset"]} if "reset" in request else {}),
        )
        if not preflight["can_stage_data"]:
            links = preflight["links"]
            if links["unhandled_finding_count"]:
                raise PreflightRefused("world_links")
            if links["opaque_record_count"]:
                raise PreflightRefused("opaque_records")
            raise PreflightRefused("no_landing")
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
        landing_dimension=request.get("reset", {}).get("landing_dimension", 0),
    )
    return position, preflight, payloads, inspected


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
    position, preflight, payloads, inspected = _changes(request, source, files)
    rftools = "rftools_identity" in request.get("reset", {})
    if rftools:
        payloads.update(transform.reseed_rftools(source, request))
    result = transform.result_inventory(
        files,
        payloads,
        request["world"],
        request["dimension"],
        reset=request.get("reset"),
    )
    if request.get("reroll_seed") and not rftools:
        fresh = transform.fresh_dimension(
            source, request, inspected["resource_identity"]
        )
        if result.keys() & fresh.keys():
            raise ValueError("New dimension files overlap retained files")
        payloads.update(fresh)
        result.update(
            {
                name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in fresh.items()
            }
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
        **({"reset": request["reset"]} if "reset" in request else {}),
        **({"reroll_seed": True} if request.get("reroll_seed") else {}),
        "snapshot": request["snapshot"],
        "archive_sha256": manifest["sha256"],
        "source": source_identity,
        "resource_identity": inspected["resource_identity"],
        "result_inventory_sha256": digest(result),
        "retained_files": len(result),
        "omitted_files": len(files.keys() - result.keys()),
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


def _verified(request, source, storage, target, *, extra_roots=()):
    _archive, _manifest, _payloads, result, plan = _inputs(
        request, source, storage, target
    )
    if plan != request["expected"] or _read(target / PLAN) != plan:
        raise ValueError("Resource source, backup or recorded plan changed")
    if {p.name for p in target.iterdir()} - {
        request["world"],
        PLAN,
        DONE,
        *extra_roots,
    }:
        raise ValueError("Foreign files in resource staging target")
    actual = inventory(
        target / request["world"],
        world_name=request["world"],
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
        allow_empty=(request.get("reset") or {}).get("fresh_world") is True,
    )
    folder = request.get("reset", {"folder": f"DIM{request['dimension']}"}).get(
        "folder"
    )
    if actual != result or (
        folder
        and (
            not request.get("reroll_seed")
            or "rftools_identity" in request.get("reset", {})
        )
        and (target / request["world"] / folder).exists()
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
        refusal = {"ok": False, "error_type": type(error).__name__}
        if isinstance(error, PreflightRefused):
            refusal["reason"] = error.reason
        print(json.dumps(refusal))
        raise SystemExit(1) from None
