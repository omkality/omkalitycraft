"""Test dependencies for mcmcp lab."""

from argparse import Namespace

import pytest

from omk.labs.mcp import mcmcp_lab as lab
from tests.fixtures.unit.launcher.game_runner import fixture


@pytest.fixture
def isolated_candidate(tmp_path, monkeypatch):
    _, release, _ = fixture(tmp_path / "fixture")
    root = tmp_path / "repo"
    (root / ".local").mkdir(parents=True)
    jar = tmp_path / "mcmcp.jar"
    jar.write_bytes(b"test jar")
    keys = tmp_path / "keys.json"
    keys.write_text("{}")
    args = Namespace(
        trusted_public_keys=keys,
        release_dir=tmp_path / "source",
        expected_release_sha256=release.digest,
        mcmcp_jar=jar,
        client_defaults=None,
        client_port=25685,
        link_port=25680,
        duration_minutes=1,
    )
    monkeypatch.setattr(lab, "PROJECT_ROOT", root)
    monkeypatch.setattr(
        lab, "_preflight", lambda _: ({"version": "2026.11.02"}, {"theoneprobe": "1"})
    )
    monkeypatch.setattr(
        lab, "PackDirectory", lambda *a: Namespace(verify=lambda: None, release=release)
    )

    class Wire:
        def __init__(self, *a):
            pass

        def serve(self):
            return self

        def __enter__(self):
            return "http://127.0.0.1:12345"

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(lab, "PackWire", Wire)
    monkeypatch.setattr(
        lab, "ReleaseClient", lambda *a: Namespace(fetch=lambda _: release)
    )

    def installer(portable, transport):
        def install(*a):
            (portable / "instances/dj2/mods").mkdir(parents=True)
            (portable / "instances/dj2/config").mkdir()
            (portable / "instances/dj2/mods/TheOneProbe.jar").write_bytes(b"author mod")

        return Namespace(install=install)

    monkeypatch.setattr(lab, "Installer", installer)
    return root, args
