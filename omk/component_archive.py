"""Bounded private TAR components. No lifecycle, extraction or live snapshots."""

import hashlib
import json
import os
import tarfile

from omk.backup_archive import MAX_MANIFEST_BYTES, validate_inventory
from omk.backup_store import _sync_directory
from omk.fs import regular, resolved
from omk.offsite_process import OffsiteError


def json_read(path):
    if not regular(path, path.parent) or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise OffsiteError("Missing, linked or oversized component manifest")
    with path.open("rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise OffsiteError("Oversized component manifest")
    return json.loads(raw)


def json_write(path, value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise OffsiteError("Component manifest exceeds bound")
    with path.open("xb") as stream:
        path.chmod(0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


def digest(path):
    if not regular(path, path.parent) or path.stat().st_nlink != 1:
        raise OffsiteError("Component requires an unlinked ordinary file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root, names, maximum):
    if resolved(root) != root.absolute() or not root.is_dir():
        raise OffsiteError("Component requires an explicit unlinked source root")
    result, total = {}, 0
    for name in names:
        if not isinstance(name, str):
            raise OffsiteError("Invalid component input name")
        path = root / name
        if (
            not isinstance(name, str)
            or name in result
            or not regular(path, root)
            or path.stat().st_nlink != 1
        ):
            raise OffsiteError("Unsafe or duplicate component input")
        before = path.stat()
        total += before.st_size
        if total > maximum or len(result) >= 20000:
            raise OffsiteError("Component exceeds its input bound")
        result[name] = {"bytes": before.st_size, "sha256": digest(path)}
        after = path.stat()
        if any(
            getattr(before, k) != getattr(after, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        ):
            raise OffsiteError("Component source changed while hashing")
    validate_inventory(
        result,
        max_expanded_bytes=maximum,
        path_policy="linux-server",
        case_sensitive=True,
    )
    return result


def file_names(root, *, excluded=()):
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] in excluded:
            continue
        if path.is_symlink() or path.is_junction():
            raise OffsiteError("Linked component source entry")
        if not path.is_dir():
            yield relative.as_posix()


def verify(archive, manifest, maximum):
    if archive.stat().st_size > maximum + 20000 * 4096 + 10240:
        raise OffsiteError("Component archive exceeds its byte bound")
    files = {
        name: {"bytes": manifest["sizes"][name], "sha256": sha}
        for name, sha in manifest["files"].items()
    }
    validate_inventory(
        files,
        max_expanded_bytes=maximum,
        path_policy="linux-server",
        case_sensitive=True,
    )
    if (
        set(manifest["sizes"]) != set(files)
        or set(manifest["modes"]) != set(files)
        or any(
            type(v) is not int or not 0 <= v <= 0o777
            for v in manifest["modes"].values()
        )
        or manifest["schema"] != 1
        or archive.stat().st_size != manifest["bytes"]
        or digest(archive) != manifest["sha256"]
    ):
        raise OffsiteError("Component archive differs from its manifest")
    seen = set()
    with tarfile.open(archive, "r:") as source:
        for member in source:
            if (
                not member.isfile()
                or member.name in seen
                or member.name not in files
                or member.size != files[member.name]["bytes"]
                or member.mode != manifest["modes"][member.name]
            ):
                raise OffsiteError("Unexpected or unsafe TAR member")
            seen.add(member.name)
            with source.extractfile(member) as stream:
                if (
                    hashlib.file_digest(stream, "sha256").hexdigest()
                    != files[member.name]["sha256"]
                ):
                    raise OffsiteError("TAR bytes differ from the frozen input")
    if seen != set(files):
        raise OffsiteError("Incomplete component archive")
    return files


def write(root, files, target, maximum, *, private=False):
    validate_inventory(
        files,
        max_expanded_bytes=maximum,
        path_policy="linux-server",
        case_sensitive=True,
    )
    with target.open("xb") as stream:
        target.chmod(0o600)
        with tarfile.open(
            fileobj=stream, mode="w", format=tarfile.PAX_FORMAT
        ) as archive:
            for name, entry in sorted(files.items()):
                path = root / name
                if not regular(path, root) or path.stat().st_nlink != 1:
                    raise OffsiteError("Component input became linked")
                member = tarfile.TarInfo(name)
                member.size = entry["bytes"]
                member.mode = 0o600 if private else path.stat().st_mode & 0o777
                with path.open("rb") as incoming:
                    archive.addfile(member, incoming)
        stream.flush()
        os.fsync(stream.fileno())
    manifest = {
        "schema": 1,
        "sha256": digest(target),
        "bytes": target.stat().st_size,
        "files": {n: e["sha256"] for n, e in files.items()},
        "sizes": {n: e["bytes"] for n, e in files.items()},
        "modes": {
            n: 0o600 if private else (root / n).stat().st_mode & 0o777 for n in files
        },
    }
    verify(target, manifest, maximum)
    if inventory(root, files, maximum) != files:
        raise OffsiteError("Stopped component changed during export")
    json_write(target.with_suffix(".json"), manifest)
    return manifest
