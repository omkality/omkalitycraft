"""Test dependencies for smoke bundle."""

import zipfile

import pytest

from launcher.install import current_platform
from launcher.paths import bundle_entrypoint
from launcher.version import VERSION
from scripts.release import smoke_bundle

ENTRYPOINT = bundle_entrypoint(current_platform())


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke_bundle, "PROJECT_ROOT", tmp_path)
    smoke_bundle.prepare()
    output = tmp_path / "build"
    unpacked = output / "OmkalityCraft"
    (unpacked / "_internal").mkdir(parents=True)
    (unpacked / ENTRYPOINT).parent.mkdir(parents=True, exist_ok=True)
    (unpacked / ENTRYPOINT).write_bytes(b"unpacked build is deliberately different")
    (unpacked / "_internal/runtime.bin").write_bytes(b"runtime dependency")
    archive = output / f"OmkalityCraft-{VERSION}-{current_platform()}.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(ENTRYPOINT, b"actual archived executable")
        zipped.writestr("_internal/runtime.bin", b"runtime dependency")
    return tmp_path, archive, unpacked
