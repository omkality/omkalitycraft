"""Prepare an exclusive, offline Core/FTB territory policy from owner environment."""

import os
import re
from pathlib import Path

POLICY_FILE = "omkalitycore-territories.properties"
FIELDS = {
    "OMK_DJ2_TERRITORIES_PER_MEMBER": ("regions_per_member", 3, 1, 50),
    "OMK_DJ2_CLAIM_REQUEST_CHUNKS": ("max_request_chunks", 1024, 1, 4096),
    "OMK_DJ2_TERRITORY_GRAPH_CHUNKS": ("max_graph_chunks", 20000, 50, 100000),
}


def territory_plan(environ=None):
    environment = os.environ if environ is None else environ
    result = {"schema": 1}
    for key, (field, default, low, high) in FIELDS.items():
        raw = environment.get(key, str(default))
        if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,6}", raw):
            raise ValueError("Invalid territory policy setting: " + key)
        value = int(raw)
        if not low <= value <= high:
            raise ValueError("Territory policy setting out of range: " + key)
        result[field] = value
    return result


def write_territory_policy(config_directory: Path, environ=None):
    """Create a new file only. Existing policies and worlds are never modified."""
    plan = territory_plan(environ)
    directory = Path(config_directory)
    if not directory.is_dir() or any(
        p.is_symlink() or p.is_junction() for p in (directory, *directory.parents)
    ):
        raise ValueError("A real offline config directory is required")
    with (directory / POLICY_FILE).open("x", encoding="ascii", newline="\n") as file:
        file.write("# Offline staging only. FTB owns claims and permissions.\n")
        for key, value in plan.items():
            file.write(f"{key}={value}\n")
    return plan
