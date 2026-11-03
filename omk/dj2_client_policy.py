"""Reviewed client-only policy for stopped DJ2 2.23.4 staging copies."""

import re
from pathlib import Path

from launcher.releases import sha256_file
from omk.backup_archive import regular_file

LOAD_SOUND_ARTIFACT_SHA256 = "0b94bea35ce762c1f9066695ddafea0091afc7696bdc310f77b5d2fa7139a13c"
MAX_CONFIG = 1024**2
BLOCK = re.compile(rb'(?m)^[ \t]*"load sounds"[ \t]*\{[ \t]*\r?\n(?P<body>[\s\S]*?)^[ \t]*\}[ \t]*\r?$')
MODE_KEY = re.compile(rb'(?m)^[ \t]*S:"\[1\] Mode"=')
MODE = re.compile(rb'(?m)^([ \t]*S:"\[1\] Mode"=)(NOTHING|MINECRAFT_AND_WORLD|MINECRAFT|WORLD)([ \t]*\r?$)')


def configure_load_sounds(path: Path, *, universal_tweaks: Path) -> dict:
    """Disable only decorative load sounds; never call on a running game.

    UT 1.20.0 dereferences a null GuiOpenEvent before the first main menu.
    Its supported NOTHING mode prevents registering that handler entirely.
    Do not generalize this workaround to a different JAR without review.
    """
    if (
        not 0 < regular_file(universal_tweaks) <= 32 * 1024**2
        or sha256_file(universal_tweaks) != LOAD_SOUND_ARTIFACT_SHA256
    ):
        raise ValueError("Unreviewed UniversalTweaks artifact")
    if not 0 < regular_file(path) <= MAX_CONFIG:
        raise ValueError("Invalid staged UniversalTweaks configuration")
    with path.open("rb") as file:
        data = file.read(MAX_CONFIG + 1)
    blocks = list(BLOCK.finditer(data))
    if len(data) > MAX_CONFIG or len(blocks) != 1:
        raise ValueError("Expected one supported load sounds category")
    body = blocks[0]["body"]
    if (
        re.search(rb"(?m)^[ \t]*[^#\r\n]*[{}]", body)
        or len(MODE_KEY.findall(body)) != 1
        or len(MODE.findall(body)) != 1
    ):
        raise ValueError("Expected one supported load sounds mode")
    previous = MODE.search(body)[2].decode("ascii")
    updated = MODE.sub(lambda match: match[1] + b"NOTHING" + match[3], body)
    if updated != body:
        start, end = blocks[0].span("body")
        path.write_bytes(data[:start] + updated + data[end:])
    return {
        "load_sound_mode": "NOTHING",
        "previous_mode": previous,
        "changed": previous != "NOTHING",
        "universal_tweaks_sha256": LOAD_SOUND_ARTIFACT_SHA256,
    }
