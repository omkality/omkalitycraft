"""Restore a stopped, owned lab backup into a new empty replacement world only."""

import hashlib
import json
import re
import stat
import zipfile
from pathlib import PurePosixPath

MAX_FILES = 20000
MAX_TOTAL = 512 * 1024**2
MAX_FILE = 128 * 1024**2
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def _destination(server, backup, destination, lab):
    if server.poll() != 0:
        raise ValueError("Full return requires a cleanly stopped owned lab")
    if not lab.name.startswith("recovery-lab-") or lab.is_symlink():
        raise ValueError("Expected owned recovery lab")
    expected = lab / "recovery-lab-return/server/lab-world"
    if destination != expected or destination.exists() or destination.is_symlink():
        raise ValueError("Full return requires the new empty replacement world")
    if backup.is_symlink() or backup.parent.resolve() != (lab / "backups").resolve():
        raise ValueError("Expected a backup belonging to this lab")
    if not destination.parent.is_dir():
        raise ValueError("Prepare replacement runtime before staging its world")
    for path in (destination.parent, destination.parent.parent):
        if path.is_symlink() or not path.resolve().is_relative_to(lab.resolve()):
            raise ValueError("Linked replacement runtime is forbidden")


def _entries(archive):
    entries = archive.infolist()
    if not 1 <= len(entries) <= MAX_FILES:
        raise ValueError("Invalid lab backup file count")
    names, prefixes, size = set(), {}, 0
    for info in entries:
        parts = info.filename.split("/")
        if (
            len(parts) < 2
            or parts[0] != "lab-world"
            or info.orig_filename != info.filename
            or info.is_dir()
            or "\\" in info.filename
            or any(
                part in ("", ".", "..")
                or any(ord(c) < 32 or c in ':*?"<>|' for c in part)
                or part.endswith((".", " "))
                or RESERVED.match(part)
                for part in parts
            )
            or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)
            or info.flag_bits & 1
        ):
            raise ValueError("Unsafe lab backup entry")
        name = info.filename.casefold()
        if name in names or not 0 <= info.file_size <= MAX_FILE:
            raise ValueError("Duplicate or oversized lab backup entry")
        names.add(name)
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            if prefixes.setdefault(prefix.casefold(), prefix) != prefix:
                raise ValueError("Ambiguous path casing in lab backup")
        size += info.file_size
    if "lab-world/level.dat" not in archive.namelist() or size > MAX_TOTAL:
        raise ValueError("Missing level or oversized lab backup")
    # Reject file/directory collisions before creating anything.
    for name in names:
        if any(str(parent) in names for parent in PurePosixPath(name).parents):
            raise ValueError("Conflicting lab backup paths")
    return entries, size


def _copy_entry(archive, info, destination):
    target = destination.joinpath(*info.filename.split("/")[1:])
    target.parent.mkdir(parents=True, exist_ok=True)
    digest, size = hashlib.sha256(), 0
    with archive.open(info) as source, target.open("xb") as output:
        while data := source.read(1024**2):
            size += len(data)
            if size > info.file_size:
                raise ValueError("Lab backup entry exceeded declared size")
            output.write(data)
            digest.update(data)
    with target.open("rb") as staged:
        actual = hashlib.file_digest(staged, "sha256").hexdigest()
    if size != info.file_size or actual != digest.hexdigest():
        raise ValueError("Staged lab backup readback mismatch")
    return actual


def stage_full_world(server, backup, expected_sha256, destination, *, lab):
    """No replacement/deletion, credentials, live server operations or promotion."""
    _destination(server, backup, destination, lab)
    with backup.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != expected_sha256:
            raise ValueError("Lab backup hash mismatch")
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            entries, size = _entries(archive)
            plan = {
                "schema": 1,
                "lab_only": True,
                "operation": "full-world-to-empty-replacement",
                "source_sha256": digest,
                "source": backup.name,
                "destination": "recovery-lab-return/server/lab-world",
                "files": len(entries),
                "uncompressed_bytes": size,
                "world_roots": sorted({i.filename.split("/")[1] for i in entries}),
                "original_world_preserved": True,
                "old_server_cleanly_stopped": True,
            }
            with (lab / "full-return-plan.json").open("x", encoding="utf-8") as file:
                json.dump(plan, file, indent=2)
            destination.mkdir()
            hashes = {
                info.filename: _copy_entry(archive, info, destination)
                for info in entries
            }
    manifest = json.dumps(hashes, sort_keys=True).encode()
    result = {
        "files": len(hashes),
        "uncompressed_bytes": size,
        "readback_verified": True,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
    }
    with (lab / "full-return-staged.json").open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
    return result
