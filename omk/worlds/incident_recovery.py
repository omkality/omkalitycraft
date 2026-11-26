"""Stage a reviewed incident edit from the latest stopped-world checkpoint."""

import base64
import hashlib
import shutil
import zipfile

from omk.backups.backup_store import (
    BackupPolicy,
    BackupStore,
    _directory,
    _json_read,
    _json_write,
    _sync_directory,
)
from omk.backups.cold_backup_worker import digest, runtime_files, source_summary
from omk.backups.stopped_world_backup import inventory
from omk.shared.nbt import write_nbt
from omk.worlds import (
    forge112_regions as anvil,
    incident_objects,
    incident_players,
    linux_restore_policy as access,
    linux_world_restore as raw,
)

PLAN = ".omk-incident-plan.json"
DONE = ".omk-incident-staged.json"
EVIDENCE = "object.nbt"
STORAGE_BYTES = 64 * 1024**2


def _file(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _access_digest(root):
    return digest(
        {
            name: _file(access._read(root, name))
            for name in access.LISTS
            if (root / name).exists() or (root / name).is_symlink()
        }
    )


def _latest_snapshot(request, storage, policy):
    if {p.name for p in storage.iterdir()} != {"store"}:
        raise ValueError("Backup publication is incomplete")
    store = BackupStore(
        storage / "store",
        policy,
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    snapshots = store._snapshots()
    if not snapshots or snapshots[-1][1].name != request["snapshot"]:
        raise ValueError("Incident stage requires the latest verified current backup")
    snapshot = snapshots[-1][1]
    return snapshot / "archive.zip", _json_read(snapshot / "manifest.json")


def _inputs(request, identity, storage, target, current):
    spec = request["incident"]
    incident_players.validate(spec)
    for path in (storage, current):
        _directory(path)
    if any(
        a.samefile(b)
        for a, b in ((storage, target), (current, target), (storage, current))
    ):
        raise ValueError("Incident stage inputs alias")
    policy = BackupPolicy(**request["policy"])
    archive, manifest = _latest_snapshot(request, storage, policy)
    files, source = source_summary(current, request)
    if files != manifest["files"]:
        raise ValueError("Stopped world differs from its latest verified backup")
    runtime = runtime_files(current)
    if digest(runtime) != source["runtime_sha256"] or runtime_files(target) != runtime:
        raise ValueError(
            "Incident candidate requires the same runtime and server properties"
        )
    access_digest = _access_digest(current)
    if _access_digest(target) != access_digest:
        raise ValueError(
            "Incident candidate access lists differ from the stopped source"
        )
    world = current / request["world"]
    view = incident_players.view_distance(current, world)
    _label, level = incident_players.document(world / "level.dat", world)
    if (
        anvil.value(anvil.value(level, "Data", 10), "DataVersion", 3)
        != incident_players.DATA_VERSION
    ):
        raise ValueError("The saved world is not in Forge 1.12.2 format")

    edits, moved, original = incident_players.player_edits(
        current, world, spec, runtime, view
    )
    affected = spec.get("quarantine")
    context = {}
    if affected and affected["kind"] != "inventory":
        path, patch, original, context = incident_objects.edit(
            current, world, affected, level, runtime
        )
        edits[path] = patch
    if not edits.keys() <= files.keys():
        raise ValueError("Incident edit is outside backup inventory")
    changes = {
        name: edit.record(current / name, files[name]["bytes"])
        if isinstance(edit, anvil.RegionEdit)
        else _file(edit)
        for name, edit in edits.items()
    }
    result = {**files, **changes}
    payload = None if original is None else write_nbt("", original)
    evidence = None
    if payload is not None:
        evidence = {
            **_file(payload),
            **context,
            "file": EVIDENCE,
            "registry_level_sha256": files[f"{world.name}/level.dat"]["sha256"],
        }
    plan = {
        **identity,
        "incident": spec,
        "snapshot": request["snapshot"],
        "archive_sha256": manifest["sha256"],
        "source": source,
        "access_sha256": access_digest,
        "changes": {
            name: {"before": files[name], "after": row} for name, row in changes.items()
        },
        "world_inventory_sha256": digest(result),
        "move": moved,
        "quarantine": evidence,
        "settings_sha256": digest(
            {k: request[k] for k in ("policy", "world_max_bytes")}
        ),
    }
    required = sum(row["bytes"] for row in result.values())
    if required > request["world_max_bytes"]:
        raise ValueError("Incident candidate exceeds expanded world budget")
    required += 4096 * len(result) + 4 * 1024**2 + len(payload or b"")
    if (
        required > policy.staging_bytes
        or shutil.disk_usage(target).free < required + policy.reserve_bytes
    ):
        raise OSError("Incident staging or disk reserve budget would be violated")
    return archive, files, result, edits, plan, payload


def _verify(request, target, source, planned, result):
    if raw._read(target / PLAN) != planned:
        raise ValueError("Incident candidate plan changed")
    files = inventory(
        target / request["world"],
        world_name=request["world"],
        max_expanded_bytes=request["world_max_bytes"],
        path_policy="linux-server",
    )
    if files != result or source_summary(source, request)[1] != planned["source"]:
        raise ValueError("Incident source or candidate differs from the verified plan")
    if digest(runtime_files(target)) != planned["source"]["runtime_sha256"]:
        raise ValueError("Incident candidate runtime changed after planning")
    if any(
        _access_digest(root) != planned["access_sha256"] for root in (source, target)
    ):
        raise ValueError("Incident access lists changed after planning")
    return {
        "operation": request["operation"],
        "plan_sha256": digest(planned),
        "world_inventory_sha256": digest(files),
        "move": planned["move"],
        "quarantine": planned["quarantine"],
        "staged": True,
        "promoted": False,
    }


def _fresh(target, world):
    if any(
        (target / name).exists() or (target / name).is_symlink()
        for name in (PLAN, DONE, raw.OWNER, raw.PLAN, raw.DONE, *raw.POLICY_MARKERS)
    ):
        raise ValueError("Incident candidate was already attempted")
    if (target / world).exists() or (target / world).is_symlink():
        raise ValueError("Incident candidate already contains a world")


def _copy_candidate(world, target, archive, original, files, edits, plan):
    _json_write(target / PLAN, plan)
    _sync_directory(target)
    (target / world).mkdir(mode=0o700)
    with zipfile.ZipFile(archive) as saved:
        for name in sorted(files):
            data = edits.get(name)
            if isinstance(data, bytes):
                raw._write_edit(target, name, data)
            else:
                raw._copy(saved, name, target, original[name])
                if data is not None:
                    data.apply(target / name)


def execute(request, storage, target, source):
    identity = raw._request(request, target)
    action = request["action"]
    if action != "verify":
        _fresh(target, request["world"])
    archive, original, files, edits, plan, payload = _inputs(
        request, identity, storage, target, source
    )
    if action == "plan":
        return plan
    if plan != request["expected"]:
        raise ValueError(
            "Incident selection, source or candidate changed after planning"
        )
    if action == "evidence" and payload is not None:
        return {"nbt": base64.b64encode(payload).decode("ascii")}
    if action not in {"apply", "verify"}:
        raise ValueError("Unknown incident staging action")
    expected_hash = (
        plan["quarantine"]["sha256"] if plan["quarantine"] is not None else None
    )
    if request.get("evidence_sha256") != expected_hash:
        raise ValueError("Private quarantine record has not been verified")
    if action == "apply":
        _copy_candidate(request["world"], target, archive, original, files, edits, plan)
    verified = _verify(request, target, source, plan, files)
    if action == "apply":
        _json_write(target / DONE, verified)
        _sync_directory(target)
    elif raw._read(target / DONE) != verified:
        raise ValueError("Incident candidate has no complete receipt")
    return verified
