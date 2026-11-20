"""Test dependencies for launcher updates."""

import zipfile
from pathlib import Path

import pytest

from omk.distribution.updates import publish_update


@pytest.fixture
def updates(tmp_path: Path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("OmkalityCraft", b"test executable payload")
        bundle.writestr("_internal/config.json", b"{}")
    repository = tmp_path / "cdn/updates"
    keys = tmp_path / "keys"
    root = publish_update(repository, keys, archive, "1.1.0", "OmkalityCraft")
    return tmp_path, repository, keys, archive, root.read_bytes()
