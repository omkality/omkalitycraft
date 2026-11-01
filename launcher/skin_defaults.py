"""Owner-provided project skin, bundled with the portable launcher."""

from pathlib import Path

SKIN_ASSETS = Path(__file__).resolve().parent / "assets" / "skins"
DEFAULT_SKIN_MODEL = "slim"


def default_skin_bytes() -> bytes:
    return (SKIN_ASSETS / "default-slim.png").read_bytes()
