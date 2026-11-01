"""Small, explicit FermiumASM workaround for a staged DJ2 server copy."""

import os
import re
from pathlib import Path

ENV = "OMK_DJ2_OPTIMIZE_FML_REMAPPER"
SETTING = re.compile(rb"(?m)^([ \t]*B:optimizeFMLRemapper=)(true|false)([ \t]*\r?$)")
KEY = re.compile(rb"(?m)^[ \t]*B:optimizeFMLRemapper=")


def configure_remapper(path: Path, *, optimize: bool | None = None) -> dict:
    """Call only on a stopped, owned staging copy, never an existing server."""
    if optimize is None:
        value = os.environ.get(ENV, "false")
        if value not in {"true", "false"}:
            raise ValueError(ENV + " must be true or false")
        optimize = value == "true"
    if type(optimize) is not bool:
        raise ValueError("Remapper policy must be boolean")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular staged FermiumASM configuration")
    with path.open("rb") as source:
        data = source.read(1024 * 1024 + 1)
    if (
        len(data) > 1024 * 1024
        or len(KEY.findall(data)) != 1
        or len(SETTING.findall(data)) != 1
    ):
        raise ValueError("Expected exactly one supported FermiumASM remapper setting")
    old = SETTING.search(data)[2] == b"true"
    updated = SETTING.sub(
        lambda match: match[1] + (b"true" if optimize else b"false") + match[3], data
    )
    if updated != data:
        # The caller owns an offline staging copy. A failed write aborts staging;
        # it is never a live config reload or an in-place production migration.
        path.write_bytes(updated)
    return {"optimize_fml_remapper": optimize, "changed": old != optimize}
