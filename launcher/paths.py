"""Portable paths belong beside the launcher, never its temporary extraction dir."""

import sys
from pathlib import Path

from omk.profiles import PROJECT_ROOT


def default_data_dir() -> Path:
    root = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else PROJECT_ROOT
    )
    return root / "userdata"
