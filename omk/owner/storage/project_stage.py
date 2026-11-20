"""Prepare a selected server release on a fresh Linux target, never boot it.

The owner holds the operation lock, mounts input read-only and exclusively owns
the empty target. A completed file receipt is NOT approval to restore historical
auth/access policy, start a container or open ingress. No lifecycle or retry over
partial files is implicit.
"""

import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import zipfile
from pathlib import PurePosixPath

from omk.backups.backup_archive import validate_inventory, verify_archive
from omk.backups.backup_store import _directory, _sync_directory
from omk.backups.offsite_process import OffsiteError
from omk.distribution import component_archive as archive
from omk.owner.storage import project_export
from omk.shared.fs import regular, resolved
from omk.worlds.linux_world_restore import _copy as copy_file

GAME = "game"
PLAN = ".omk-project-stage-plan.json"
DONE = ".omk-project-staged.json"
_FIELDS = {
    "schema",
    "operation",
    "world",
    "source",
    "target",
    "selection",
    "settings",
    "runtime_inventory_sha256",
    "world_inventory_sha256",
    "files",
    "bytes",
}
_FLAGS = {
    "quarantine_required": True,
    "ready_for_players": False,
    "boot_allowed": False,
    "current_policy_reconciled": False,
}


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _roots(source, target):
    if sys.platform != "linux":
        raise OffsiteError("Project release staging requires Linux")
    for path in (source, target):
        _directory(path)
        if not path.is_absolute() or resolved(path) != path.absolute():
            raise OffsiteError("Project staging requires explicit unlinked directories")
    if source.is_relative_to(target) or target.is_relative_to(source):
        raise OffsiteError("Project source and stage must be separate")
    if target.stat().st_mode & 0o077:
        raise OffsiteError("Project target requires a private directory")


def _context(operation, world, selection, settings):
    if (
        not isinstance(operation, str)
        or not re.fullmatch(r"[a-f0-9]{32}", operation)
        or not isinstance(world, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", world)
        or not isinstance(selection, dict)
        or set(selection) != {"project_sha256", "release_identity"}
        or not isinstance(selection["project_sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", selection["project_sha256"])
        or not isinstance(settings, dict)
        or set(settings)
        != {
            "max_bytes",
            "world_bytes",
            "runtime_bytes",
            "auth_bytes",
            "operator_bytes",
            "reserve_bytes",
        }
        or any(
            type(v) is not int or not (0 if k == "reserve_bytes" else 1) <= v <= 1024**4
            for k, v in settings.items()
        )
        or settings["auth_bytes"] > 128 * 1024**2
        or settings["operator_bytes"] > 1024**3
    ):
        raise OffsiteError("Invalid project stage request")
    identity = project_export._release_identity(selection["release_identity"])
    return {
        "project_sha256": selection["project_sha256"],
        "release_identity": identity,
    }, dict(settings)


def _selected(source, world, selection, settings):
    if archive.digest(source / "project.json") != selection["project_sha256"]:
        raise OffsiteError("Project stage differs from the selected closed snapshot")
    project_export.verify(
        source, settings, expected_release_identity=selection["release_identity"]
    )
    runtime = archive.json_read(source / "runtime.json")
    files = archive.verify(source / "runtime.tar", runtime, settings["runtime_bytes"])
    world_manifest = archive.json_read(source / "world.json")
    world_files = world_manifest["files"]
    verify_archive(
        source / "world.zip",
        world_files,
        world_manifest["sha256"],
        max_expanded_bytes=settings["world_bytes"],
        path_policy="linux-server",
    )
    if (
        world + "/level.dat" not in world_files
        or any(not name.startswith(world + "/") for name in world_files)
        or any(name == world or name.startswith(world + "/") for name in files)
    ):
        raise OffsiteError("Project runtime and selected world layout differ")
    combined = {**files, **world_files}
    if len(combined) != len(files) + len(world_files):
        raise OffsiteError("Project runtime collides with the selected world")
    validate_inventory(
        combined,
        max_expanded_bytes=min(
            1024**4, settings["world_bytes"] + settings["runtime_bytes"]
        ),
        path_policy="linux-server",
        case_sensitive=True,
    )
    if archive.digest(source / "project.json") != selection["project_sha256"]:
        raise OffsiteError("Selected project changed during verification")
    return files, runtime["modes"], world_files


def _derive(source, target, *, operation, world, selection, settings):
    _roots(source, target)
    selection, settings = _context(operation, world, selection, settings)
    files, modes, world_files = _selected(source, world, selection, settings)
    expected = {
        "schema": 1,
        "operation": operation,
        "world": world,
        "source": str(source),
        "target": str(target),
        "selection": selection,
        "settings": settings,
        "runtime_inventory_sha256": _digest({"files": files, "modes": modes}),
        "world_inventory_sha256": _digest(world_files),
        "files": len(files) + len(world_files),
        "bytes": sum(e["bytes"] for e in files.values())
        + sum(e["bytes"] for e in world_files.values()),
    }
    return expected, files, modes, world_files


def _space(target, expected):
    required = expected["bytes"] + expected["files"] * 4096 + 2 * 65536
    if (
        shutil.disk_usage(target).free
        < required + expected["settings"]["reserve_bytes"]
    ):
        raise OSError("Project stage free-space reserve would be violated")


def _empty(target):
    if any(target.iterdir()):
        raise OffsiteError(
            "Project stage requires an empty owned target; never repeat a partial copy"
        )


def plan(source, target, *, operation, world, selection, settings):
    """Read-only preflight; caller persists this plan before requesting writes."""
    _roots(source, target)
    _empty(target)
    expected, _files, _modes, _world_files = _derive(
        source,
        target,
        operation=operation,
        world=world,
        selection=selection,
        settings=settings,
    )
    _space(target, expected)
    return expected


def _bound(source, target, expected):
    if (
        not isinstance(expected, dict)
        or set(expected) != _FIELDS
        or type(expected["schema"]) is not int
        or expected["schema"] != 1
    ):
        raise OffsiteError("Invalid saved project stage plan")
    actual, files, modes, world_files = _derive(
        source,
        target,
        **{k: expected[k] for k in ("operation", "world", "selection", "settings")},
    )
    if _digest(actual) != _digest(expected):
        raise OffsiteError("Project stage plan or source changed")
    return actual, files, modes, world_files


def write_record(path, value):
    if len(json.dumps(value).encode()) > 65536:
        raise OffsiteError("Project stage record exceeds bound")
    archive.json_write(path, value)


def _read(path, target):
    if (
        not regular(path, target)
        or path.stat().st_nlink != 1
        or path.stat().st_size > 65536
    ):
        raise OffsiteError("Missing or unsafe project stage record")
    return archive.json_read(path)


class _RuntimeReader:
    """Use the existing checked file copier without TAR extraction or links."""

    def __init__(self, incoming, files, modes):
        self.incoming, self.files, self.modes = incoming, files, modes

    def open(self, name):
        member = self.incoming.getmember(name)
        if (
            not member.isfile()
            or member.size != self.files[name]["bytes"]
            or member.mode != self.modes[name]
        ):
            raise OffsiteError("Project runtime member changed before copying")
        return self.incoming.extractfile(member)


def _check_files(target, files, modes, world_files, settings):
    game = target / GAME
    _directory(game)
    expected_dirs = set()
    for name in (*files, *world_files):
        expected_dirs.update(
            str(p) for p in PurePosixPath(name).parents if str(p) != "."
        )
    found_files, found_dirs = set(), set()
    for path in game.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise OffsiteError("Linked project stage entry")
        name = path.relative_to(game).as_posix()
        (found_dirs if path.is_dir() else found_files).add(name)
    if found_files != set(files) | set(world_files) or found_dirs != expected_dirs:
        raise OffsiteError("Project stage layout differs from its plan")
    if (
        archive.inventory(game, files, settings["runtime_bytes"]) != files
        or archive.inventory(game, world_files, settings["world_bytes"]) != world_files
    ):
        raise OffsiteError("Project stage bytes differ from selected archives")
    if any(
        (game / name).stat().st_mode & 0o777 != mode for name, mode in modes.items()
    ):
        raise OffsiteError("Project runtime mode differs from its archive")
    if any((game / name).stat().st_mode & 0o777 != 0o600 for name in world_files):
        raise OffsiteError("Project world file lost its private mode")


def stage(source, target, *, expected):
    """Copy once; any partial or uncertain output is retained, never overwritten."""
    _roots(source, target)
    _empty(target)
    actual, files, modes, world_files = _bound(source, target, expected)
    _space(target, actual)
    write_record(target / PLAN, actual)
    game = target / GAME
    game.mkdir(mode=0o700)
    _sync_directory(target)
    with tarfile.open(source / "runtime.tar", "r:") as incoming:
        reader = _RuntimeReader(incoming, files, modes)
        for name, entry in files.items():
            copy_file(reader, name, game, entry)
            with (game / name).open("rb") as written:
                os.fchmod(written.fileno(), modes[name])
                os.fsync(written.fileno())
    with zipfile.ZipFile(source / "world.zip") as incoming:
        for name, entry in world_files.items():
            copy_file(incoming, name, game, entry)
    _bound(source, target, actual)
    _check_files(target, files, modes, world_files, actual["settings"])
    if {p.name for p in target.iterdir()} != {PLAN, GAME} or _digest(
        _read(target / PLAN, target)
    ) != _digest(actual):
        raise OffsiteError("Project stage layout or intent changed before sealing")
    receipt = {**actual, **_FLAGS}
    write_record(target / DONE, receipt)
    return {"staged": True, **receipt}


def verify(source, target, *, expected):
    """Read-only recovery of a completed receipt; no repair and no boot approval."""
    actual, files, modes, world_files = _bound(source, target, expected)
    if {p.name for p in target.iterdir()} != {PLAN, DONE, GAME}:
        raise OffsiteError("Project stage has no complete isolated layout")
    receipt = {**actual, **_FLAGS}
    if _digest(_read(target / PLAN, target)) != _digest(actual) or _digest(
        _read(target / DONE, target)
    ) != _digest(receipt):
        raise OffsiteError("Project stage has no complete bound receipt")
    _check_files(target, files, modes, world_files, actual["settings"])
    return {"verified": True, **receipt}
