"""Preserve verified pre-change evidence independently of normal backup retention."""

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime

from omk.backups.backup_archive import MAX_MANIFEST_BYTES, SHA256, verify_archive
from omk.backups.backup_store import _sync_directory
from omk.owner import admin_backups
from omk.owner.admin import (
    AdminError,
    _private_path,
    _read_json,
    _require_private,
    _write_private,
)
from omk.owner.admin_actions import _within
from omk.owner.incident_summary import _java_stack, summarize_incident
from omk.owner.private_journal import parse_time
from omk.shared.fs import regular

_CASE_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
_SNAPSHOT = re.compile(r"snapshot-[a-f0-9]{32}")
_MAX_CASES = 8
_MAX_BYTES = 8 * 1024**3
_RESERVE = 512 * 1024**2
_JSON_LIMIT = 2 * 1024**2
_DIAGNOSTIC_LIMIT = 32 * 1024
_CASE_FILES = {"archive.zip", "manifest.json", "incident.json"}


def _private_file(path, root):
    if not regular(path, root) or path.stat().st_nlink != 1:
        raise AdminError("Expected a private file without links")
    _require_private(path, secret=True)
    return path


def _incident(config, args, history):
    descriptor = _private_path(config.private, args.incident)
    entry = _read_json(descriptor, config.private)
    fields = {"time", "dimension", "position", "kind", "diagnostic"}
    if not fields <= set(entry) <= fields | {"tps", "mspt"}:
        raise AdminError("Invalid incident field set")
    if not isinstance(entry["time"], str):
        raise AdminError("Invalid incident time")
    at = parse_time(entry["time"])
    start, end = history["coverage"]["requested_ms"]
    point = entry["position"]
    if not (
        start <= round(at.timestamp() * 1000) < end
        and type(entry["dimension"]) is int
        and entry["dimension"] == args.dimension
        and isinstance(point, list)
        and len(point) == 3
        and all(type(value) is int for value in point)
        and _within(point, args.area)
        and entry["kind"] in ("minecraft_crash", "jvm_crash", "thread_dump")
    ):
        raise AdminError("Incident time, dimension and location must match the search")
    for key, maximum in (("tps", 20), ("mspt", 600_000)):
        if key in entry and not (
            type(entry[key]) in (int, float)
            and 0 <= entry[key] <= maximum
            and math.isfinite(entry[key])
        ):
            raise AdminError("Invalid incident tick metrics")
    diagnostic = _private_path(config.private, entry.pop("diagnostic"))
    with _private_file(diagnostic, config.private).open("rb") as stream:
        raw = stream.read(_DIAGNOSTIC_LIMIT + 1)
    if not raw or len(raw) > _DIAGNOSTIC_LIMIT:
        raise AdminError("Provide a diagnostic excerpt of at most 32 KiB")
    detail = raw.decode("utf-8")
    summary = summarize_incident({"kind": entry["kind"], "detail": detail})
    causes, frames = _java_stack(detail.splitlines())
    if not frames and not summary["native_module"]:
        raise AdminError("The incident diagnostic contains no recognised stack frames")
    if summary["level_dimension"] not in (None, entry["dimension"]):
        raise AdminError("Diagnostic dimension differs from the incident location")
    if summary["subject"] and summary["subject"]["block"] not in (None, point):
        raise AdminError("Diagnostic block differs from the incident location")
    return {
        **entry,
        "time": at.isoformat(),
        "diagnostic": summary,
        "frames": frames,
        "exception_types": causes,
    }


def _snapshot(config, args, incident):
    record = admin_backups.read_record(config, args.backup_operation)
    result, source = record.get("result") or {}, record.get("source") or {}
    folder = _private_path(config.private, args.snapshot)
    if not (
        record.get("stage") == "complete"
        and record["server"] == args.server
        and result.get("verified") is True
        and _SNAPSHOT.fullmatch(result.get("id", ""))
        and folder.name == result["id"]
        and parse_time(record["created_at"]) >= parse_time(incident["time"])
        and SHA256.fullmatch(source.get("runtime_sha256", ""))
    ):
        raise AdminError(
            "Choose a verified cold snapshot of this server taken after the incident"
        )
    _require_private(folder, directory=True)
    path = _private_file(folder / "manifest.json", folder)
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise AdminError("Snapshot manifest is too large")
    with path.open("rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise AdminError("Snapshot manifest is too large")
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise AdminError("Invalid private snapshot manifest")
    archive = _private_file(folder / "archive.zip", folder)
    world = record["target"]["world"]
    inventory = manifest.get("files")
    length = archive.stat().st_size
    if not (
        set(manifest) == {"schema", "sequence", "sha256", "files", "bytes"}
        and manifest["schema"] == 1
        and result["sequence"] == manifest["sequence"]
        and result["sha256"] == manifest["sha256"]
        and SHA256.fullmatch(manifest["sha256"])
        and type(manifest["bytes"]) is int
        and 0 < length == manifest["bytes"] <= _MAX_BYTES
        and isinstance(inventory, dict)
        and len(inventory) == source["files"]
        and all(name.startswith(world + "/") for name in inventory)
        and hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
        == source["inventory_sha256"]
    ):
        raise AdminError("Snapshot manifest differs from the verified operation")
    return archive, manifest, record


def _copy(source, destination, size):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    with (
        source.open("rb") as incoming,
        os.fdopen(os.open(destination, flags, 0o600), "wb") as outgoing,
    ):
        remaining = size
        while remaining:
            data = incoming.read(min(remaining, 1024**2))
            if not data:
                break
            outgoing.write(data)
            remaining -= len(data)
        if remaining or incoming.read(1):
            raise AdminError("Snapshot size changed while copying")
        outgoing.flush()
        os.fsync(outgoing.fileno())


def _budget(directory, total):
    for count, entry in enumerate(directory.iterdir(), 1):
        if (
            not _CASE_NAME.fullmatch(entry.name)
            or entry.is_symlink()
            or entry.is_junction()
        ):
            raise AdminError(
                "Inspect the unexpected or incomplete action evidence directory"
            )
        _require_private(entry, directory=True)
        if {p.name for p in entry.iterdir()} != _CASE_FILES:
            raise AdminError("Inspect the incomplete action evidence case")
        total += sum(
            _private_file(entry / filename, entry).stat().st_size
            for filename in _CASE_FILES
        )
        if count >= _MAX_CASES or total > _MAX_BYTES:
            raise AdminError(
                "Action evidence quota reached; archive an older case first"
            )


def preserve_case(config, args, history):
    """Bind the selected interval and diagnostic to a copied and verified cold snapshot."""
    if not _CASE_NAME.fullmatch(args.evidence):
        raise AdminError("Choose a lowercase case name with letters, digits or hyphens")
    incident = _incident(config, args, history)
    source, manifest, record = _snapshot(config, args, incident)
    directory = _private_path(config.private, "action-evidence")
    destination = directory / args.evidence
    size = manifest["bytes"] + MAX_MANIFEST_BYTES + _JSON_LIMIT
    payload = {
        "schema": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "incident": incident,
        "history": history,
        "backup": {
            "operation": record["operation"],
            "id": record["result"]["id"],
            "world": record["target"]["world"],
            "runtime_sha256": record["source"]["runtime_sha256"],
            "archive_sha256": manifest["sha256"],
        },
    }
    if len(json.dumps(payload, ensure_ascii=False, indent=2).encode()) > _JSON_LIMIT:
        raise AdminError("The selected incident history exceeds the export limit")
    with admin_backups.locked(config):
        directory.mkdir(mode=0o700, exist_ok=True)
        _require_private(directory, directory=True)
        if destination.exists():
            raise AdminError("An evidence case with this name already exists")
        _budget(directory, size)
        if size > _MAX_BYTES or shutil.disk_usage(directory).free < size + _RESERVE:
            raise AdminError("Insufficient disk space for the verified evidence copy")
        with tempfile.TemporaryDirectory(
            prefix=".pending-", dir=directory
        ) as temporary:
            staging = directory / os.path.basename(temporary)
            _require_private(staging, directory=True)
            _copy(source, staging / "archive.zip", manifest["bytes"])
            verify_archive(
                staging / "archive.zip",
                manifest["files"],
                manifest["sha256"],
                max_expanded_bytes=record["settings"]["world_max_bytes"],
                path_policy="linux-server",
            )
            _write_private(staging / "manifest.json", config.private, manifest)
            _write_private(staging / "incident.json", config.private, payload)
            _sync_directory(staging)
            staging.rename(destination)
            _sync_directory(directory)
    return destination
