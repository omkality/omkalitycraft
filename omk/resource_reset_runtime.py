"""Seal the reviewed runtime around an existing cold reset candidate.

Source/store remain readonly. Only an unused, previously staged target may be
written once. A complete receipt can be verified after interruption; no lifecycle,
cutover, retry over partial files, deletion or permission changes are performed.
"""

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path, PurePosixPath

from omk import resource_reset_stage as stage
from omk.backup_archive import regular_file, validate_inventory
from omk.backup_store import _json_write, _sync_directory
from omk.cold_backup_worker import digest, runtime_files
from omk.fs import regular
from omk.linux_restore_policy import LISTS, _flag, _read
from omk.linux_world_restore import _read as read_record

PLAN = ".omk-resource-runtime-plan.json"
DONE = ".omk-resource-runtime-ready.json"
DIRECTORIES = {".omk/tmp", ".omk/java-home"}
ADAPTER = "forge112-cold-runtime-v1"


def files(root, world):
    """Known runtime plus current access/EULA; never logs, caches or backups."""
    hashes = runtime_files(root)
    props = _read(root, "server.properties", limit=65536)
    _flag(props)
    if re.findall(rb"^level-name=([^\r\n]+)\r?$", props, re.M) != [world.encode()]:
        raise ValueError("Runtime world name differs from the staged world")
    eula = _read(root, "eula.txt", limit=65536)
    if re.findall(rb"^eula=(true|false)\r?$", eula, re.M) != [b"true"]:
        raise ValueError("Source must already have accepted the Minecraft EULA")
    for name in LISTS:
        data = _read(root, name)
        rows = json.loads(data)
        if (
            not isinstance(rows, list)
            or len(rows) > 10000
            or any(not isinstance(row, dict) for row in rows)
            or (name == "ops.json" and rows)
        ):
            raise ValueError("Invalid access list or unexpected game operators")
        hashes[name] = hashlib.sha256(data).hexdigest()
    hashes["eula.txt"] = hashlib.sha256(eula).hexdigest()
    result = {}
    for name, sha in hashes.items():
        path = root / name
        if not regular(path, root) or path.stat().st_nlink != 1:
            raise ValueError("Runtime paths must be ordinary unshared files")
        result[name] = {"sha256": sha, "bytes": regular_file(path)}
    # This is a Linux-only runtime, not a portable world ZIP. Forge packs can
    # legitimately contain distinct case-sensitive resource/config paths. Keep
    # each safe path exactly; do not impose the archive's cross-file casefold.
    if len(result) > 20000 or sum(v["bytes"] for v in result.values()) > 8 * 1024**3:
        raise ValueError("Runtime inventory exceeds reviewed bound")
    for name, entry in result.items():
        validate_inventory(
            {name: entry}, max_expanded_bytes=8 * 1024**3, path_policy="linux-server"
        )
    return result


def _request(request):
    if not isinstance(request, dict) or request.get("action") not in {
        "runtime-plan",
        "runtime-stage",
        "runtime-verify",
    }:
        raise ValueError("Invalid runtime preparation action")
    required = request["action"] != "runtime-plan"
    if ("runtime_expected" in request) is not required:
        raise ValueError("Invalid frozen runtime request")
    data = {k: v for k, v in request.items() if k != "runtime_expected"}
    data["action"] = "verify"
    stage._request(data)
    return data


def _roots(manifest):
    return {n.split("/")[0] for n in manifest} | {".omk", PLAN, DONE}


def _receipt(request, source, storage, target, manifest):
    data = {k: v for k, v in request.items() if k != "runtime_expected"}
    data["action"] = "verify"
    receipt = stage._verified(
        data, source, storage, target, extra_roots=_roots(manifest)
    )
    if read_record(target / stage.DONE) != receipt:
        raise ValueError("Data candidate has no complete unchanged receipt")
    return receipt


def _plan(request, source, storage, target):
    # _inputs checks stopped-world/backup/runtime/preflight and all path aliases.
    data = _request(request)
    _archive, _snapshot, _edits, world, plan = stage._inputs(
        data, source, storage, target
    )
    if plan != request["expected"]:
        raise ValueError("Data plan changed before runtime preparation")
    manifest = files(source, request["world"])
    receipt = _receipt(request, source, storage, target, manifest)
    # Re-read every source runtime/policy file, never persist their contents.
    if manifest != files(source, request["world"]):
        raise ValueError("Source runtime changed during planning")
    return manifest, {
        "schema": 1,
        "adapter": ADAPTER,
        "operation": request["operation"],
        "data_plan_sha256": digest(plan),
        "data_receipt_sha256": digest(receipt),
        "world_inventory_sha256": digest(world),
        "world_bytes": sum(f["bytes"] for f in world.values()),
        "runtime_inventory_sha256": digest(manifest),
        "runtime_files": len(manifest),
        "runtime_bytes": sum(f["bytes"] for f in manifest.values()),
        "directories": sorted(DIRECTORIES),
        "ready_for_start": False,
        "ready_for_players": False,
    }


def _layout(root, world, manifest, *, complete):
    allowed_files = set(manifest) | {PLAN, DONE, stage.PLAN, stage.DONE}
    allowed_dirs = set(DIRECTORIES)
    for name in allowed_files | DIRECTORIES:
        allowed_dirs.update(
            str(p) for p in PurePosixPath(name).parents if str(p) != "."
        )
    seen = {}
    for directory, folders, names in os.walk(root, followlinks=False):
        base = Path(directory)
        if base == root and world in folders:
            folders.remove(world)
        for name in folders:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or path.is_junction() or relative not in allowed_dirs:
                raise ValueError("Unexpected runtime directory")
        for name in names:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if (
                relative not in allowed_files
                or not regular(path, root)
                or path.stat().st_nlink != 1
            ):
                raise ValueError("Unexpected runtime file")
            if relative in manifest:
                length = regular_file(path)
                with path.open("rb") as stream:
                    sha = hashlib.file_digest(stream, "sha256").hexdigest()
                seen[relative] = {"bytes": length, "sha256": sha}
    if complete and (
        seen != manifest or any(not (root / n).is_dir() for n in DIRECTORIES)
    ):
        raise ValueError("Runtime candidate inventory differs or is incomplete")
    return seen


def _fresh(target, world):
    if {p.name for p in target.iterdir()} != {world, stage.PLAN, stage.DONE}:
        raise ValueError("Runtime target already attempted or has foreign files")


def _space(request, target, plan):
    cost = plan["runtime_bytes"] + plan["runtime_files"] * 4096 + 4 * 1024**2
    total = cost + plan["world_bytes"] + request["expected"]["retained_files"] * 4096
    if total > request["policy"]["staging_bytes"] or (
        shutil.disk_usage(target).free < cost + request["policy"]["reserve_bytes"]
    ):
        raise OSError(
            "Combined world/runtime staging budget or reserve would be violated"
        )


def _copy(source, target, name, expected):
    src, dst = source / name, target / name
    if not regular(src, source) or src.stat().st_nlink != 1:
        raise ValueError("Runtime source changed before copy")
    dst.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    sha, length = hashlib.sha256(), 0
    with src.open("rb") as original, dst.open("xb") as output:
        dst.chmod(0o600)
        while block := original.read(1024**2):
            length += len(block)
            if length > expected["bytes"]:
                raise ValueError("Runtime source grew during copy")
            sha.update(block)
            output.write(block)
        output.flush()
        os.fsync(output.fileno())
    if {"bytes": length, "sha256": sha.hexdigest()} != expected:
        raise ValueError("Runtime source bytes changed during copy")
    parent = dst.parent
    while parent.is_relative_to(target):
        _sync_directory(parent)
        if parent == target:
            break
        parent = parent.parent


def _verify(request, source, storage, target):
    manifest, plan = _plan(request, source, storage, target)
    if plan != request["runtime_expected"] or read_record(target / PLAN) != plan:
        raise ValueError("Runtime plan or source changed")
    _layout(target, request["world"], manifest, complete=True)
    return {
        "operation": request["operation"],
        "runtime_plan_sha256": digest(plan),
        "runtime_inventory_sha256": digest(manifest),
        "world_inventory_sha256": plan["world_inventory_sha256"],
        "runtime_prepared": True,
        "promoted": False,
        "ready_for_start": False,
        "ready_for_players": False,
    }


def execute(
    request, source=Path("/server"), storage=Path("/backup"), target=Path("/target")
):
    _request(request)
    if request["action"] == "runtime-verify":
        receipt = _verify(request, source, storage, target)
        if read_record(target / DONE) != receipt:
            raise ValueError("Runtime candidate has no complete receipt")
        return receipt
    _fresh(target, request["world"])
    manifest, plan = _plan(request, source, storage, target)
    _space(request, target, plan)
    if request["action"] == "runtime-plan":
        return plan
    if plan != request["runtime_expected"]:
        raise ValueError("Runtime input changed after planning")
    _json_write(target / PLAN, plan)
    _sync_directory(target)
    for name in sorted(manifest):
        _copy(source, target, name, manifest[name])
    for name in sorted(DIRECTORIES):
        (target / name).mkdir(parents=True, exist_ok=True, mode=0o700)
        _sync_directory(target / name)
        _sync_directory((target / name).parent)
    receipt = _verify(request, source, storage, target)
    _json_write(target / DONE, receipt)
    _sync_directory(target)
    return receipt


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("Runtime request exceeds limit")
        print(json.dumps({"ok": True, "result": execute(json.loads(raw))}))
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
