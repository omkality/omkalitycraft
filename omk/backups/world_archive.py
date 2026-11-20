"""Validate common world ZIP entry metadata before reading or extracting files."""

import re
import stat
from pathlib import PurePosixPath
from zipfile import ZipFile, ZipInfo

from omk.backups.backup_archive import validate_path_policy

MAX_FILES = 20000
MAX_TOTAL = 512 * 1024**2
MAX_FILE = 128 * 1024**2
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def world_archive_entries(
    archive: ZipFile,
    *,
    world_name: str = "lab-world",
    path_policy: str = "portable",
    max_expanded_bytes: int | None = None,
) -> tuple[list[ZipInfo], int]:
    """Return regular entries and bounded expanded size for one owned world root."""
    validate_path_policy(path_policy)
    if max_expanded_bytes is not None and (
        type(max_expanded_bytes) is not int or not 1 <= max_expanded_bytes <= 1024**4
    ):
        raise ValueError("Invalid archive expanded limit")
    total_limit = MAX_TOTAL if max_expanded_bytes is None else max_expanded_bytes
    file_limit = MAX_FILE if max_expanded_bytes is None else max_expanded_bytes
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", world_name):
        raise ValueError("Invalid archive world root")
    entries = archive.infolist()
    if not 1 <= len(entries) <= MAX_FILES:
        raise ValueError("Invalid world backup file count")
    names: set[str] = set()
    prefixes: dict[str, str] = {}
    size = 0
    for info in entries:
        parts = info.filename.split("/")
        if (
            len(parts) < 2
            or parts[0] != world_name
            or info.orig_filename != info.filename
            or info.is_dir()
            or "\\" in info.filename
            or any(
                part in ("", ".", "..")
                or any(ord(c) < 32 or c in ':*?"<>|' for c in part)
                or part.endswith((".", " "))
                or (path_policy == "portable" and RESERVED.match(part))
                for part in parts
            )
            or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)
            or info.flag_bits & 1
        ):
            raise ValueError("Unsafe world backup entry")
        name = info.filename.casefold()
        if name in names or not 0 <= info.file_size <= file_limit:
            raise ValueError("Duplicate or oversized world backup entry")
        names.add(name)
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            if prefixes.setdefault(prefix.casefold(), prefix) != prefix:
                raise ValueError("Ambiguous path casing in world backup")
        size += info.file_size
    if world_name + "/level.dat" not in archive.namelist() or size > total_limit:
        raise ValueError("Missing level or oversized world backup")
    # Reject file/directory collisions before creating anything.
    for name in names:
        if any(str(parent) in names for parent in PurePosixPath(name).parents):
            raise ValueError("Conflicting world backup paths")
    return entries, size
