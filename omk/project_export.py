"""Capture one stopped project into a new private flat export set.

The trusted owner holds its shared operation lock and supplies checkpoints from
actual Docker inspection before and after this call. No stop/start, auth reset,
schedule or transfer is implicit. A project manifest is published LAST.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import UTC, datetime

from omk import (
    auth_state_archive,
    component_archive as archive,
)
from omk.backup_archive import verify_archive
from omk.backup_store import _sync_directory
from omk.fs import resolved
from omk.offsite_process import OffsiteError
from omk.restic_transport import IDENTITY, OPERATION, signature
from omk.stopped_world_backup import inventory as world_inventory
from omk.storage_policy import storage_plan

ROLES = {"world": "zip", "auth": "tar", "runtime": "tar", "operator": "tar"}
FILES = {"project.json"} | {
    f"{role}.{suffix}" for role, kind in ROLES.items() for suffix in (kind, "json")
}


def policy(environment=None):
    env = os.environ if environment is None else environment
    result = {}
    for name, default, upper in (
        ("MAX_BYTES", 16 * 1024**3, 1024**4),
        ("WORLD_BYTES", 16 * 1024**3, 1024**4),
        ("RUNTIME_BYTES", 8 * 1024**3, 1024**4),
        ("AUTH_BYTES", 128 * 1024**2, 128 * 1024**2),
        ("OPERATOR_BYTES", 64 * 1024**2, 1024**3),
    ):
        raw = env.get("OMK_PROJECT_EXPORT_" + name, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 15
            or not 1 <= int(raw) <= upper
        ):
            raise OffsiteError("Invalid project export budget")
        result[name.lower()] = int(raw)
    budget = storage_plan(env)
    if not budget["ok"]:
        raise OffsiteError(budget["error"])
    result["reserve_bytes"] = budget["budgets_gib"]["reserve"] * 1024**3
    return result


def closed(value):
    try:
        if set(value) != {"game", "auth"}:
            raise ValueError
        for role, r in value.items():
            if (
                set(r) - ({"config_sha256"} if role == "auth" else set())
                != {
                    "container_id",
                    "image_id",
                    "volume",
                    "started_at",
                    "finished_at",
                    "running",
                    "restarting",
                    "exit_code",
                    "oom_killed",
                }
                or not IDENTITY.fullmatch(r["container_id"])
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", r["image_id"])
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", r["volume"])
                or any(
                    r[k] is not False for k in ("running", "restarting", "oom_killed")
                )
                or type(r["exit_code"]) is not int
                or r["exit_code"] != 0
            ):
                raise ValueError
            if role == "auth" and not IDENTITY.fullmatch(r["config_sha256"]):
                raise ValueError
            start, finish = (
                datetime.fromisoformat(r[k].replace("Z", "+00:00"))
                for k in ("started_at", "finished_at")
            )
            if start.tzinfo != UTC or finish.tzinfo != UTC or finish < start:
                raise ValueError
        if (
            value["game"]["container_id"] == value["auth"]["container_id"]
            or value["game"]["volume"] == value["auth"]["volume"]
        ):
            raise ValueError
    except KeyError, TypeError, ValueError:
        raise OffsiteError(
            "Project export requires distinct cleanly stopped game and auth sources"
        ) from None


def validate_sources(destination, roots, scope):
    if sys.platform != "linux":
        raise OffsiteError("Project export capture is a Linux owner operation")
    if (
        any(resolved(p) != p.absolute() or not p.is_dir() for p in roots)
        or len(set(roots)) != 3
        or any(p.is_relative_to(q) for p in roots for q in roots if p != q)
        or resolved(destination) != destination.absolute()
        or any(
            destination.is_relative_to(p) or p.is_relative_to(destination)
            for p in roots
        )
    ):
        raise OffsiteError(
            "Export and source roots must be explicit, separate and unlinked"
        )
    if (
        set(scope) != {"project", "server", "pack_version", "operation"}
        or any(
            not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", v)
            for v in scope.values()
        )
        or not OPERATION.fullmatch(scope["operation"])
    ):
        raise OffsiteError("Invalid project export scope")


def capture(
    destination,
    *,
    game,
    auth,
    operator,
    operator_files,
    world_zip,
    world_json,
    world_name,
    scope,
    checkpoint,
    settings,
):
    # checkpoint must independently bind these mounts to the allowlisted volumes.
    validate_sources(destination, (game, auth, operator), scope)
    before = checkpoint()
    closed(before)
    # Detach nested mutable checkpoint objects supplied by a controller.
    before = json.loads(json.dumps(before))
    scope = json.loads(json.dumps(scope))
    started = datetime.now(UTC).isoformat()
    world = archive.json_read(world_json)
    if (
        set(world) != {"schema", "sequence", "sha256", "files", "bytes"}
        or type(world["schema"]) is not int
        or world["schema"] != 1
        or type(world["sequence"]) is not int
        or world["sequence"] < 1
        or type(world["bytes"]) is not int
        or world["bytes"] != world_zip.stat().st_size
    ):
        raise OffsiteError("Invalid source world manifest")
    files = world_inventory(
        game / world_name,
        world_name=world_name,
        max_expanded_bytes=settings["world_bytes"],
        path_policy="linux-server",
    )
    if world["files"] != files:
        raise OffsiteError("World archive belongs to another stopped source state")
    verify_archive(
        world_zip,
        files,
        world["sha256"],
        max_expanded_bytes=settings["world_bytes"],
        path_policy="linux-server",
    )
    inventories = {
        "auth": archive.inventory(
            auth, archive.file_names(auth), settings["auth_bytes"]
        ),
        "runtime": archive.inventory(
            game,
            archive.file_names(
                game, excluded=(world_name, "logs", "crash-reports", "backups")
            ),
            settings["runtime_bytes"],
        ),
        "operator": archive.inventory(
            operator, operator_files, settings["operator_bytes"]
        ),
    }
    if (
        not {"drasl.db", "key.pkcs8"} <= inventories["auth"].keys()
        or not {"operator.toml", "drasl.toml"} <= inventories["operator"].keys()
    ):
        raise OffsiteError("Missing authentication or operator identity material")
    if (
        inventories["operator"]["drasl.toml"]["sha256"]
        != before["auth"]["config_sha256"]
    ):
        raise OffsiteError("Drasl configuration differs from the stopped source")
    if any(
        n.split("/")[0] in {"offsite", "exports", "staging"}
        for n in inventories["operator"]
    ):
        raise OffsiteError("Do not export transport credentials or recursive staging")
    projected = world_zip.stat().st_size + 32 * 1024**2
    projected += sum(
        e["bytes"] + 4096 for inv in inventories.values() for e in inv.values()
    )
    required = projected + 2 * sum(e["bytes"] for e in inventories["auth"].values())
    if (
        projected > settings["max_bytes"]
        or shutil.disk_usage(destination.parent).free
        < required + settings["reserve_bytes"]
    ):
        raise OffsiteError("Project export would exceed staging budget or free reserve")
    destination.mkdir(mode=0o700)
    with (
        world_zip.open("rb") as source,
        (destination / "world.zip").open("xb") as target,
    ):
        (destination / "world.zip").chmod(0o600)
        shutil.copyfileobj(source, target, length=1024**2)
        target.flush()
        os.fsync(target.fileno())
    if archive.digest(destination / "world.zip") != world["sha256"]:
        raise OffsiteError("World archive changed during export")
    archive.json_write(destination / "world.json", world)
    for role, root in (("auth", auth), ("runtime", game), ("operator", operator)):
        archive.write(
            root,
            inventories[role],
            destination / (role + ".tar"),
            settings[role + "_bytes"],
            private=role in {"auth", "operator"},
        )
    # Existing offline Drasl validator reads the new copy, never the source DB.
    with tempfile.TemporaryDirectory(
        prefix="auth-check-", dir=destination
    ) as temporary:
        from pathlib import Path  # noqa: PLC0415

        auth_state_archive.restore(Path(temporary), destination / "auth.tar")
    if world_inventory(
        game / world_name,
        world_name=world_name,
        max_expanded_bytes=settings["world_bytes"],
        path_policy="linux-server",
    ) != files or any(
        archive.inventory(root, names, settings[role + "_bytes"]) != inventories[role]
        for role, root, names in (
            ("auth", auth, archive.file_names(auth)),
            (
                "runtime",
                game,
                archive.file_names(
                    game, excluded=(world_name, "logs", "crash-reports", "backups")
                ),
            ),
            ("operator", operator, operator_files),
        )
    ):
        raise OffsiteError("Project source changed before closure")
    after = checkpoint()
    closed(after)
    if before != after:
        raise OffsiteError(
            "Project lifecycle changed during export; retain unsealed staging"
        )
    entries = {
        p.name: {"bytes": p.stat().st_size, "sha256": archive.digest(p)}
        for p in destination.iterdir()
    }
    if sum(e["bytes"] for e in entries.values()) > settings["max_bytes"]:
        raise OffsiteError("Prepared project set exceeds its byte bound")
    manifest = {
        "schema": 1,
        "kind": "omk-closed-project-export",
        "scope": scope,
        "closed_sources": before,
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "files": entries,
        "settings": settings,
        "quarantine_required": True,
        "ready_for_players": False,
    }
    archive.json_write(destination / "project.json", manifest)
    _sync_directory(destination.parent)
    return verify(destination, settings)


def verify(directory, settings):
    # Hash the exact set before allowing transport; no extraction or lifecycle.
    if resolved(directory) != directory.absolute() or not directory.is_dir():
        raise OffsiteError("Project export requires an unlinked directory")
    if {p.name for p in directory.iterdir()} != FILES:
        raise OffsiteError("Incomplete or foreign project export set")
    manifest = archive.json_read(directory / "project.json")
    if (
        manifest.get("schema") != 1
        or manifest.get("kind") != "omk-closed-project-export"
        or manifest.get("settings") != settings
        or manifest.get("ready_for_players") is not False
        or manifest.get("quarantine_required") is not True
        or set(manifest.get("files", {})) != FILES - {"project.json"}
    ):
        raise OffsiteError("Invalid project export manifest")
    closed(manifest["closed_sources"])
    if sum(p.stat().st_size for p in directory.iterdir()) > settings["max_bytes"]:
        raise OffsiteError("Sealed export exceeds its byte bound")
    for name, entry in manifest["files"].items():
        p = directory / name
        if p.stat().st_size != entry["bytes"] or archive.digest(p) != entry["sha256"]:
            raise OffsiteError("Project component differs from its sealed set")
    transport_limits = {"max_files": 9, "max_bytes": settings["max_bytes"]}
    return {
        "manifest": manifest,
        "export": signature(directory, transport_limits),
        "ready_for_players": False,
        "quarantine_required": True,
    }
