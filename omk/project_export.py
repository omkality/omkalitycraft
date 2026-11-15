"""Capture one stopped project into a new private flat export set.

The trusted owner holds its shared operation lock and supplies checkpoints from
actual Docker inspection before and after this call. No stop/start, auth reset,
schedule or transfer is implicit. A project manifest is published LAST.
Optional release context is an owner declaration, not Git or client-signature
attestation. Release selection uses the saved full identity, never one rebuilt
from the candidate being checked. Authentication rollback is not implied.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import UTC, datetime

from launcher.releases import PLATFORMS
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
_RELEASE_CONTEXT = {"source_commit", "client_manifests", "declared_state_contract"}
_RELEASE_BINDING = {
    "game_image_id",
    "runtime_archive_sha256",
    "runtime_manifest_sha256",
}
_RELEASE_MANIFEST = {
    "schema",
    "kind",
    "scope",
    "closed_sources",
    "started_at",
    "finished_at",
    "files",
    "settings",
    "quarantine_required",
    "ready_for_players",
    "release_identity",
}


def _release_context(value):
    if (
        not isinstance(value, dict)
        or set(value) != _RELEASE_CONTEXT
        or not isinstance(value["source_commit"], str)
        or not re.fullmatch(r"[a-f0-9]{40}", value["source_commit"])
        or not isinstance(value["declared_state_contract"], str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value["declared_state_contract"])
        or not isinstance(value["client_manifests"], dict)
        or not 1 <= len(value["client_manifests"]) <= len(PLATFORMS)
        or any(
            platform not in PLATFORMS
            or not isinstance(digest, str)
            or not IDENTITY.fullmatch(digest)
            for platform, digest in value["client_manifests"].items()
        )
    ):
        raise OffsiteError("Invalid declared project release context")
    return {
        "source_commit": value["source_commit"],
        "declared_state_contract": value["declared_state_contract"],
        "client_manifests": dict(sorted(value["client_manifests"].items())),
    }


def _release_identity(value):
    if not isinstance(value, dict) or set(value) != _RELEASE_CONTEXT | _RELEASE_BINDING:
        raise OffsiteError("Missing or invalid project release identity")
    context = _release_context({key: value[key] for key in _RELEASE_CONTEXT})
    if (
        not isinstance(value["game_image_id"], str)
        or not re.fullmatch(r"sha256:[a-f0-9]{64}", value["game_image_id"])
        or any(
            not isinstance(value[key], str) or not IDENTITY.fullmatch(value[key])
            for key in ("runtime_archive_sha256", "runtime_manifest_sha256")
        )
    ):
        raise OffsiteError("Invalid project release runtime identity")
    return {**context, **{key: value[key] for key in _RELEASE_BINDING}}


def _bound_release(context, sources, files):
    try:
        return {
            **context,
            "game_image_id": sources["game"]["image_id"],
            "runtime_archive_sha256": files["runtime.tar"]["sha256"],
            "runtime_manifest_sha256": files["runtime.json"]["sha256"],
        }
    except KeyError, TypeError:
        raise OffsiteError("Invalid project release runtime binding") from None


def _seal(destination, manifest, settings, release):
    if release is not None:
        manifest["release_identity"] = _bound_release(
            release, manifest["closed_sources"], manifest["files"]
        )
    archive.json_write(destination / "project.json", manifest)
    _sync_directory(destination.parent)
    return verify(
        destination,
        settings,
        expected_release_identity=manifest.get("release_identity"),
    )


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
    release_context=None,
):
    # checkpoint must independently bind these mounts to the allowlisted volumes.
    validate_sources(destination, (game, auth, operator), scope)
    release = None if release_context is None else _release_context(release_context)
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
        "schema": 1 if release is None else 2,
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
    return _seal(destination, manifest, settings, release)


def verify(directory, settings, *, expected_release_identity=None):
    # Hash the exact set before allowing transport; no extraction or lifecycle.
    expected = (
        None
        if expected_release_identity is None
        else _release_identity(expected_release_identity)
    )
    if resolved(directory) != directory.absolute() or not directory.is_dir():
        raise OffsiteError("Project export requires an unlinked directory")
    if {p.name for p in directory.iterdir()} != FILES:
        raise OffsiteError("Incomplete or foreign project export set")
    manifest = archive.json_read(directory / "project.json")
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema")) is not int
        or manifest["schema"] not in {1, 2}
        or manifest.get("kind") != "omk-closed-project-export"
        or manifest.get("settings") != settings
        or manifest.get("ready_for_players") is not False
        or manifest.get("quarantine_required") is not True
        or set(manifest.get("files", {})) != FILES - {"project.json"}
    ):
        raise OffsiteError("Invalid project export manifest")
    closed(manifest["closed_sources"])
    if manifest["schema"] == 2:
        if set(manifest) != _RELEASE_MANIFEST:
            raise OffsiteError("Invalid project release manifest fields")
        identity = _release_identity(manifest["release_identity"])
        context = {key: identity[key] for key in _RELEASE_CONTEXT}
        if identity != _bound_release(
            context, manifest["closed_sources"], manifest["files"]
        ):
            raise OffsiteError("Project release does not bind its runtime components")
    else:
        if "release_identity" in manifest:
            raise OffsiteError("Release identity requires project export schema 2")
        identity = None
    if expected is not None and expected != identity:
        raise OffsiteError("Project export differs from the selected release identity")
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
