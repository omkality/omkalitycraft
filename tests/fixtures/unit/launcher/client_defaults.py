"""Test dependencies for client defaults."""

from dataclasses import replace
from pathlib import Path

from tests.fixtures.unit.launcher.game_runner import fixture


def setup(tmp_path: Path):
    folder, release, _ = fixture(tmp_path)
    font = folder / "resourcepacks/FM_NewFont/pack.mcmeta"
    font.parent.mkdir(parents=True)
    font.write_text('{"pack":{"pack_format":3}}')
    defaults = {
        "required_resourcepacks": ["FM_NewFont"],
        "language": "ru_ru",
        "force_unicode_font": False,
        "servers": [{"id": "dj2", "name": "DJ2 тест", "address": "127.0.0.1:25576"}],
    }
    release = replace(release, launch={**release.launch, "client_defaults": defaults})
    return folder, release
