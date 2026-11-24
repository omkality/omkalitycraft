"""Locate launcher data independently of the current working directory."""

import sys
from pathlib import Path

from omk.shared.profiles import PROJECT_ROOT

MACOS_APP = "OmkalityCraft.app"


def bundle_entrypoint(platform: str) -> str:
    """Return the executable path inside a newly built launcher archive."""
    if platform.startswith("windows-"):
        return "OmkalityCraft.exe"
    if platform.startswith("macos-"):
        return f"{MACOS_APP}/Contents/MacOS/OmkalityCraft"
    return "OmkalityCraft"


def default_data_dir() -> Path:
    """Keep new Mac app data writable, while recognizing an adjacent portable install."""
    if not getattr(sys, "frozen", False):
        return PROJECT_ROOT / "userdata"
    binary = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        macos = binary.parent
        contents = macos.parent
        app = contents.parent
        if (
            macos.name == "MacOS"
            and contents.name == "Contents"
            and app.suffix == ".app"
        ):
            # Existing installs can reuse their downloads by placing the app beside them.
            if any((app.parent / name).is_dir() for name in ("userdata", "instances")):
                return app.parent / "userdata"
            return Path.home() / "Library/Application Support/OmkalityCraft/userdata"
    return binary.parent / "userdata"
