"""Write an opt-in Core/FTB spawn plan into a fresh, offline staging directory."""

import os
import re
from pathlib import Path

ENV_RADIUS = "OMK_DJ2_SPAWN_RADIUS"
POLICY_FILE = "omkalitycore-spawn.properties"


def spawn_plan(environ=None):
    values = os.environ if environ is None else environ
    value = values.get(ENV_RADIUS, "300")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,4}", value):
        raise ValueError(f"Invalid {ENV_RADIUS}")
    radius = int(value)
    # Bounded also by Core's independent 10,000-chunk startup budget.
    if not 1 <= radius <= 768:
        raise ValueError(f"Invalid {ENV_RADIUS}")
    minimum, maximum = -radius // 16, radius // 16
    return {
        "dimension": 0,
        "radius": radius,
        "chunk_min": minimum,
        "chunk_max": maximum,
        "chunks": (maximum - minimum + 1) ** 2,
        "protected_min": minimum * 16,
        "protected_max": maximum * 16 + 15,
    }


def write_spawn_policy(config_directory: Path, environ=None):
    """Exclusive creation only; this function cannot update an existing policy."""
    plan = spawn_plan(environ)
    folder = Path(config_directory)
    if not folder.is_dir() or any(p.is_symlink() for p in (folder, *folder.parents)):
        raise ValueError("A real offline config directory is required")
    radius = plan["radius"]
    with (folder / POLICY_FILE).open("x", encoding="ascii", newline="\n") as file:
        file.write(
            "# Offline staging plan. FTB owns protection; no forced chunk loading.\n"
            f"version=1\nzones=0:{-radius}:{radius}:{-radius}:{radius}\n"
        )
    return plan
