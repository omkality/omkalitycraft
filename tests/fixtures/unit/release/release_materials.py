"""Test dependencies for release materials."""

from importlib import metadata

import pytest

from launcher.install import current_platform
from launcher.version import VERSION
from scripts.release import release_materials as materials


@pytest.fixture
def bundle(tmp_path):
    folder = tmp_path / "bundle"
    fonts = folder / "_internal/launcher/assets/fonts"
    fonts.mkdir(parents=True)
    for name in ["OFL.txt", "Monocraft-LICENSE.txt"]:
        (fonts / name).write_bytes(b"synthetic font license")
    (
        folder
        / (
            "OmkalityCraft.exe"
            if current_platform().startswith("windows")
            else "OmkalityCraft"
        )
    ).write_bytes(b"synthetic executable")
    materials.json_file(
        folder / "release-info.json",
        {
            "schema": 1,
            "version": VERSION,
            "platform": current_platform(),
            "python": "3.14.2",
            "pyinstaller": metadata.version("pyinstaller"),
        },
    )
    return folder
