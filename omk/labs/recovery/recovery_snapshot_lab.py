"""Prepare an unambiguous overworld-only WorldEdit ZIP for the disposable lab."""

import re
import shutil
import zipfile


def prepare_overworld_snapshot(backup, target):
    """No extraction, dimension guessing, or existing-file replacement."""
    with zipfile.ZipFile(backup) as source:
        entries = source.infolist()
        if len(entries) > 20000:
            raise ValueError("Too many lab backup entries")
        selected = [
            info
            for info in entries
            if info.filename == "lab-world/level.dat"
            or re.fullmatch(r"lab-world/region/r\.-?\d+\.-?\d+\.mca", info.filename)
        ]
        names = {info.filename for info in selected}
        if (
            len(names) != len(selected)
            or "lab-world/level.dat" not in names
            or len(names) < 2
        ):
            raise ValueError("Missing or duplicate overworld snapshot entries")
        size = 0
        for info in selected:
            size += info.file_size
            if not 0 < info.file_size <= 128 * 1024**2 or size > 512 * 1024**2:
                raise ValueError("Overworld snapshot exceeds lab size limit")
        with zipfile.ZipFile(
            target, "x", zipfile.ZIP_DEFLATED, compresslevel=1
        ) as output:
            for info in selected:
                with (
                    source.open(info) as incoming,
                    output.open(info.filename, "w") as outgoing,
                ):
                    shutil.copyfileobj(incoming, outgoing, length=1024**2)
    return {
        "dimension": 0,
        "files": len(selected),
        "uncompressed_bytes": size,
        "excluded_entries": len(entries) - len(selected),
    }
