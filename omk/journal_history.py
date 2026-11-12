"""Bounded, immutable history of completed nightly scopes; never world data.

Every archive file contains a small identity/hash header and the exact original
JSON bytes. Publish and fsync all five files before unlinking any live journal.
The shared owner lock makes a partial move resumable without a second writer.
History is never evicted: old recovery references must remain resolvable.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime

from omk.admin import AdminError, _private_path, _read_json
from omk.backup_store import _sync_directory
from omk.fs import regular
from omk.storage_policy import storage_plan

AREAS = {"nightly", "maintenance", "backups", "ingress"}
MAX_RECORD = 65536
MAX_HEADER = 512
MAX_FILES = 20000


def path(config, area, operation, *, archived=False):
    if (
        area not in AREAS
        or not isinstance(operation, str)
        or not re.fullmatch(r"[a-f0-9]{32}", operation)
    ):
        raise AdminError("Invalid owner journal identifier")
    name = area + "/" + operation + ".json"
    if archived:
        name = "journal-history/" + area + "/" + operation + ".omkj"
    return _private_path(config.private, name)


def present(config, area, operation):
    return any(
        path(config, area, operation, archived=archived).exists()
        for archived in (False, True)
    )


def writable(config, area, operation):
    if path(config, area, operation, archived=True).exists():
        raise AdminError("Archived owner journals are read-only; inspect their status")


def raw_private(config, file, maximum):
    if (
        not regular(file, config.private)
        or file.stat().st_nlink != 1
        or (os.name != "nt" and file.stat().st_mode & 0o077)
    ):
        raise AdminError("Owner journal must be a private, unlinked regular file")
    with file.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise AdminError("Owner journal exceeds its size bound")
    return raw


def decode(raw, area, operation):
    try:
        header, payload = raw.split(b"\n", 1)
        value = json.loads(header)
        record = json.loads(payload)
        if (
            len(header) > MAX_HEADER
            or len(payload) > MAX_RECORD
            or set(value) != {"schema", "area", "operation", "nightly", "sha256"}
            or type(value["schema"]) is not int
            or value["schema"] != 1
            or value["area"] != area
            or value["operation"] != operation
            or not isinstance(value["nightly"], str)
            or not re.fullmatch(r"[a-f0-9]{32}", value["nightly"])
            or value["sha256"] != hashlib.sha256(payload).hexdigest()
            or not isinstance(record, dict)
            or record.get("operation") != operation
            or (area == "nightly" and value["nightly"] != operation)
        ):
            raise ValueError
    except ValueError, TypeError, KeyError, UnicodeError:
        raise AdminError("Invalid or damaged owner journal history") from None
    return value, payload, record


def archived(config, area, operation):
    file = path(config, area, operation, archived=True)
    result = decode(
        raw_private(config, file, MAX_HEADER + MAX_RECORD + 1), area, operation
    )
    if area != "nightly":
        root = read(config, "nightly", result[0]["nightly"])
        try:
            kinds = {
                "maintenance": ["maintenance"],
                "backups": ["backup"],
                "ingress": ["close", "open"],
            }
            if (
                root["stage"] != "complete"
                or root["server"] != result[2]["server"]
                or operation not in [root["children"][k] for k in kinds[area]]
            ):
                raise ValueError
        except KeyError, TypeError, ValueError:
            raise AdminError(
                "Archived journal has no matching completed nightly root"
            ) from None
    return result


def read(config, area, operation):
    live = path(config, area, operation)
    old = path(config, area, operation, archived=True)
    if not old.exists():
        return _read_json(live, config.private)
    _, payload, record = archived(config, area, operation)
    if live.exists() and raw_private(config, live, MAX_RECORD) != payload:
        raise AdminError("Live journal conflicts with its immutable history")
    return record


def policy(environment=None):
    env = os.environ if environment is None else environment
    enabled = env.get("OMK_JOURNAL_ARCHIVE_ENABLED", "false")
    if not isinstance(enabled, str) or enabled not in {"true", "false"}:
        raise AdminError("Invalid OMK_JOURNAL_ARCHIVE_ENABLED")
    result = {"enabled": enabled == "true"}
    for key, default, minimum, maximum in (
        ("KEEP_CYCLES", 7, 1, 100),
        ("BATCH_CYCLES", 32, 1, 100),
        ("MAX_FILES", 10000, 5, MAX_FILES),
        ("MAX_BYTES", 256 * 1024**2, 1, 2 * 1024**3),
    ):
        raw = env.get("OMK_JOURNAL_ARCHIVE_" + key, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 12
            or not minimum <= int(raw) <= maximum
        ):
            raise AdminError("Invalid OMK_JOURNAL_ARCHIVE_" + key)
        result[key.lower()] = int(raw)
    project = storage_plan(env)
    if not project["ok"]:
        raise AdminError(project["error"])
    result["reserve_bytes"] = project["budgets_gib"]["reserve"] * 1024**3
    return result


def inventory(config):
    root = _private_path(config.private, "journal-history")
    result = {"files": 0, "bytes": 0}
    if not root.exists():
        return result
    for folder in root.iterdir():
        if (
            folder.name not in AREAS
            or not folder.is_dir()
            or folder.stat().st_dev != root.stat().st_dev
        ):
            raise AdminError("Unexpected owner history directory")
        _private_path(config.private, str(folder.relative_to(config.private)))
        for file in folder.iterdir():
            path(config, folder.name, file.stem, archived=True)
            if file.suffix != ".omkj" or not regular(file, config.private):
                raise AdminError("Unexpected owner history file")
            result["files"] += 1
            result["bytes"] += file.stat().st_size
            if result["files"] > MAX_FILES:
                raise AdminError("Owner history inventory exceeds its file bound")
    return result


def instant(value):
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None:
            raise ValueError
    except ValueError, TypeError:
        raise AdminError("Invalid completed journal time") from None
    return result.astimezone(UTC)


def scope(config, root):
    try:
        return checked_scope(config, root)
    except KeyError, TypeError, ValueError:
        raise AdminError("Incomplete completed nightly history") from None


def checked_scope(config, root):
    """Validate persisted cross-references only; never plan/replay a child."""
    from omk import (  # noqa: PLC0415
        admin_backups as backups,
        admin_maintenance as maintenance,
        ingress,
    )

    if root["stage"] != "complete":
        raise AdminError("Only completed nightly scopes can enter history")
    ids = root["children"]
    m = maintenance.read_record(config, ids["maintenance"])
    b = backups.read_record(config, ids["backup"])
    c, o = (ingress.read(config, ids[k]) for k in ("close", "open"))
    records = [("maintenance", m), ("backups", b), ("ingress", c), ("ingress", o)]
    if (
        m["stage"] != "complete"
        or b["stage"] != "complete"
        or c["stage"] != "confirmed"
        or o["stage"] != "confirmed"
        or c["wanted"] != "closed"
        or o["wanted"] != "open"
        or root["warned"] != root["settings"]["calendar"]["warnings_seconds"]
        or m["target"] != root["target"]
        or m["binding"] != root["binding"]
        or m["initial"] != root["initial"]
        or m["ingress"] != root["gate"]
        or m["settings"] != root["settings"]["maintenance"]
        or m["runtime"]["runtime_sha256"] != root["disk"]["runtime_sha256"]
        or m["backup_operation"] != b["operation"]
        or m["resumed"] != root["resumed"]["source"]
        or b["target"] != root["target"]
        or b["settings"] != root["settings"]["backup"]
        or b["checkpoint"] != m["checkpoint"]
        or b["source"]["runtime_sha256"] != root["disk"]["runtime_sha256"]
        or any(
            r["server"] != root["server"]
            or instant(r["created_at"]) < instant(root["created_at"])
            for _, r in records
        )
        or any(r["operator_root"] != root["operator_root"] for r in (m, b))
        or any(
            r["deployment"] != root["gate"]
            or r["lifecycle"] != root["settings"]["maintenance"]
            for r in (c, o)
        )
    ):
        raise AdminError("Completed nightly history has inconsistent children")
    return [*records, ("nightly", root)]


def publish(config, area, operation, value):
    target = path(config, area, operation, archived=True)
    target.parent.parent.mkdir(exist_ok=True, mode=0o700)
    target.parent.mkdir(exist_ok=True, mode=0o700)
    # The parent directory entries must survive the loss of the owner process.
    for folder in (target.parent, target.parent.parent, config.private):
        _sync_directory(folder)
    fd, name = tempfile.mkstemp(
        prefix=".history-" + operation + "-", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
        _sync_directory(target.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def temporaries(config, area, operation):
    folder = path(config, area, operation, archived=True).parent
    result = []
    for file in folder.glob(".history-" + operation + "-*.tmp"):
        if not re.fullmatch(
            r"\.history-" + operation + r"-[a-z0-9_]{8}\.tmp", file.name
        ):
            raise AdminError("Unknown owner history staging file")
        raw_private(config, file, MAX_HEADER + MAX_RECORD + 1)
        result.append(file)
        if len(result) > 16:
            raise AdminError("Too many interrupted owner history staging files")
    return result


def collect_files(config, root):
    files, extra = [], {"files": 0, "bytes": 0}
    for area, record in scope(config, root):
        operation = record["operation"]
        live = path(config, area, operation)
        old = path(config, area, operation, archived=True)
        if old.exists():
            header, raw, _ = archived(config, area, operation)
            if header["nightly"] != root["operation"]:
                raise AdminError("Journal already belongs to another archived scope")
            if live.exists() and raw_private(config, live, MAX_RECORD) != raw:
                raise AdminError("Live journal conflicts with history before cleanup")
            packed = None
        else:
            raw = raw_private(config, live, MAX_RECORD)
            if json.loads(raw) != record:
                raise AdminError("Journal changed while collecting history")
            header = {
                "schema": 1,
                "area": area,
                "operation": operation,
                "nightly": root["operation"],
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            packed = json.dumps(header, separators=(",", ":")).encode() + b"\n" + raw
            extra["files"] += 1
            extra["bytes"] += len(packed)
        files.append((area, operation, live, raw, packed))
    return files, extra


def move_scope(config, root, settings):
    files, extra = collect_files(config, root)
    # All originals have just been checked. A killed publisher may leave an
    # unpublished temp copy; these exact scope-owned copies are safe to discard
    # under the OS lock, including a partially written one. No history is pruned.
    for area, operation, _, _, _ in files:
        for temporary in temporaries(config, area, operation):
            temporary.unlink()
            _sync_directory(temporary.parent)
    current = inventory(config)
    if any(current[k] + extra[k] > settings["max_" + k] for k in extra):
        raise AdminError("Owner history is full; no journal was removed or evicted")
    # Account for allocated blocks and directories as well as logical bytes.
    needed = extra["bytes"] + extra["files"] * 8192
    destination = _private_path(config.private, "journal-history")
    if (
        shutil.disk_usage(destination if destination.exists() else config.private).free
        < settings["reserve_bytes"] + needed
    ):
        raise AdminError("Owner history would violate the project disk reserve")
    for area, operation, _, _, packed in files:
        if packed is not None:
            publish(config, area, operation, packed)
    # Verify the entire group before the first unlink. Root is removed last, so
    # the next scan can finish any process-interrupted partial publication/move.
    for area, operation, live, raw, _ in files:
        header, stored, _ = archived(config, area, operation)
        if stored != raw or header["nightly"] != root["operation"]:
            raise AdminError("Owner history verification failed before cleanup")
        if live.exists() and raw_private(config, live, MAX_RECORD) != raw:
            raise AdminError("Live owner journal changed before cleanup")
    for _, _, live, _, _ in files:
        if live.exists():
            live.unlink()
            _sync_directory(live.parent)


def compact(config, server, environment=None):
    from omk import (  # noqa: PLC0415
        admin_backups as backups,
        nightly_cycle as cycle,
    )

    settings = policy(environment)
    if not settings["enabled"]:
        return {"enabled": False, "archived_cycles": 0}
    if server not in config.servers:
        raise AdminError("History server is not allowlisted")
    with backups.locked(config):
        folder = _private_path(config.private, "nightly")
        rows = []
        if folder.exists():
            for index, file in enumerate(folder.iterdir()):
                if index >= 1000:
                    raise AdminError("Active nightly inventory exceeds its bound")
                r = cycle.read(config, file.stem)
                if r["server"] == server and r["stage"] == "complete":
                    rows.append(r)
        rows.sort(key=lambda r: (instant(r["created_at"]), r["operation"]))
        older = rows[: max(0, len(rows) - settings["keep_cycles"])]
        # A partially published group is recovery work, even if the policy now
        # keeps more recent cycles. Finish it before selecting additional groups.
        pending = [
            r
            for r in rows
            if any(
                path(config, area, item["operation"], archived=True).exists()
                or temporaries(config, area, item["operation"])
                for area, item in scope(config, r)
            )
        ]
        selected = {r["operation"]: r for r in [*pending, *older]}
        batch = list(selected.values())[: settings["batch_cycles"]]
        for r in batch:
            move_scope(config, r, settings)
        return {"enabled": True, "archived_cycles": len(batch), **inventory(config)}
