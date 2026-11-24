"""Locate launcher data independently of the current working directory."""

import sys
from pathlib import Path

from omk.shared.profiles import PROJECT_ROOT

MACOS_APP = "OmkalityCraft.app"
MACOS_RUNTIME = "OmkalityCraftRuntime"
BRAND_ICON = Path(__file__).resolve().parent / "assets/branding/icon.png"


def bundle_entrypoint(platform: str) -> str:
    """Return the executable path inside a newly built launcher archive."""
    if platform.startswith("windows-"):
        return "OmkalityCraft.exe"
    if platform.startswith("macos-"):
        return f"{MACOS_APP}/Contents/MacOS/OmkalityCraft"
    return "OmkalityCraft"


def default_data_dir() -> Path:
    """Keep portable data beside the executable or its macOS app bundle."""
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
            return app.parent / "userdata"
    return binary.parent / "userdata"
