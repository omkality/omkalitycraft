"""Test dependencies for launcher update sources."""

import zipfile
from pathlib import Path

import pytest

from launcher.install import current_platform
from omk.distribution.updates import publish_update


def asset(version="1.1.0", platform=None):
    platform = platform or current_platform()
    return (
        "https://github.com/omkality/omkalitycraft/releases/download/"
        f"launcher-v{version}/OmkalityCraft-{version}-{platform}.zip"
    )


@pytest.fixture
def release(tmp_path: Path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("OmkalityCraft", b"test executable, never executed")
    repository, keys = tmp_path / "cdn/updates", tmp_path / "keys"
    root = publish_update(
        repository,
        keys,
        archive,
        "1.1.0",
        "OmkalityCraft",
        github_asset_url=asset(),
    )
    return tmp_path, repository, root.read_bytes(), archive.read_bytes()
