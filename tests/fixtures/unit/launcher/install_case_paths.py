"""Test dependencies for install case paths."""

import contextlib
import json
import shutil
from collections.abc import Generator

import pytest

from launcher.install import (
    Installer,
    ReleaseClient,
    current_platform,
)
from launcher.releases import Release
from omk.distribution.publish import build_release
from tests.fixtures.http import serve
from tests.fixtures.unit.launcher import signed_install

repository = signed_install.repository


@pytest.fixture
def case_install(repository, tmp_path):
    _, original, envelope, keys, key = repository
    installer = Installer(
        tmp_path / "portable", ReleaseClient("http://127.0.0.1", keys)
    )

    @contextlib.contextmanager
    def generation(
        name, payload, version
    ) -> Generator[tuple[Release, list[tuple[str, int]]]]:
        root = tmp_path / f"generation-{version}"
        files = root / "releases/dj2" / current_platform() / "files"
        shutil.copytree(original, files)
        path = files / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        signed = build_release(
            files,
            pack_id="dj2",
            version=version,
            minecraft="1.12.2",
            platform=current_platform(),
            launch=envelope["manifest"]["launch"],
            key=key,
        )
        (files.parent / "manifest.json").write_text(json.dumps(signed))
        with serve(root) as (url, requests):
            installer.client = ReleaseClient(url, keys)
            release = installer.client.fetch("dj2")
            requests.clear()
            yield release, requests

    return installer, generation
