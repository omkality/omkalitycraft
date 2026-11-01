"""Bounded readback verification of an archive against a trusted input inventory."""

import hashlib
import re
import stat
import zipfile
from pathlib import PurePosixPath

MAX_MANIFEST_BYTES = 8 * 1024**2
MAX_FILES = 20000
MAX_EXPANDED_BYTES = 512 * 1024**2
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
SHA256 = re.compile(r"[a-f0-9]{64}")


def regular_file(path):
    if (
        path.is_symlink()
        or path.is_junction()
        or not stat.S_ISREG(path.lstat().st_mode)
    ):
        raise ValueError("Expected an ordinary file without links")
    return path.stat().st_size


def validate_inventory(files):
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("Invalid backup inventory")
    total, names, prefixes = 0, set(), {}
    for name, entry in files.items():
        parts = name.split("/") if isinstance(name, str) else []
        if (
            not parts
            or len(name.encode("utf-8")) > 1024
            or any(
                part in ("", ".", "..")
                or len(part.encode("utf-8")) > 255
                or any(ord(c) < 32 or c in '\\:*?"<>|' for c in part)
                or part.endswith((".", " "))
                or RESERVED.match(part)
                for part in parts
            )
        ):
            raise ValueError("Unsafe backup inventory path")
        folded = name.casefold()
        if folded in names:
            raise ValueError("Ambiguous backup path")
        names.add(folded)
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            if prefixes.setdefault(prefix.casefold(), prefix) != prefix:
                raise ValueError("Ambiguous backup path casing")
        if (
            not isinstance(entry, dict)
            or set(entry) != {"bytes", "sha256"}
            or type(entry["bytes"]) is not int
            or not 0 <= entry["bytes"] <= MAX_EXPANDED_BYTES
            or not isinstance(entry["sha256"], str)
            or not SHA256.fullmatch(entry["sha256"])
        ):
            raise ValueError("Invalid backup inventory entry")
        total += entry["bytes"]
    if total > MAX_EXPANDED_BYTES or any(
        str(parent) in names for name in names for parent in PurePosixPath(name).parents
    ):
        raise ValueError("Oversized or conflicting backup inventory")


def verify_archive(path, files, expected_sha256=None):
    """Read every byte/CRC; an FTB success message is never the inventory source."""
    validate_inventory(files)
    regular_file(path)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("Backup archive hash mismatch")
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) != len(files) or {i.filename for i in entries} != set(
                files
            ):
                raise ValueError("Backup archive inventory mismatch")
            for info in entries:
                if (
                    info.orig_filename != info.filename
                    or info.is_dir()
                    or info.flag_bits & 1
                    or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)
                    or info.file_size != files[info.filename]["bytes"]
                ):
                    raise ValueError("Unsafe or incomplete backup archive entry")
                with archive.open(info) as incoming:
                    actual, size = hashlib.sha256(), 0
                    while data := incoming.read(1024**2):
                        size += len(data)
                        if size > info.file_size:
                            raise ValueError("Backup entry exceeded its declared size")
                        actual.update(data)
                if (
                    size != info.file_size
                    or actual.hexdigest() != files[info.filename]["sha256"]
                ):
                    raise ValueError("Backup file readback mismatch")
    return digest
