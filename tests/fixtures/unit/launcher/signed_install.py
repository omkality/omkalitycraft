"""Test dependencies for signed install."""

import json
from pathlib import Path

import pytest

from launcher.install import (
    current_platform,
)
from omk.distribution.publish import build_release, signing_key


@pytest.fixture
def repository(tmp_path: Path):
    root = tmp_path / "cdn"
    folder = root / "releases" / "dj2" / current_platform()
    files = folder / "files"
    for name in [
        "runtime/bin/java",
        "agent.jar",
        "forge.jar",
        "mods/old.jar",
        "config/test.cfg",
    ]:
        path = files / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((name * 1000).encode())
    public = tmp_path / "public.json"
    key = signing_key(tmp_path / "private.pem", public)
    launch = {
        "java": "runtime/bin/java",
        "agent": "agent.jar",
        "classpath": ["forge.jar"],
        "main_class": "net.minecraft.launchwrapper.Launch",
        "assets": "assets",
        "natives": "natives",
        "game_args": ["--username", "{username}"],
    }
    envelope = build_release(
        files,
        pack_id="dj2",
        version="1.0",
        minecraft="1.12.2",
        platform=current_platform(),
        launch=launch,
        key=key,
    )
    (folder / "manifest.json").write_text(json.dumps(envelope))
    return root, files, envelope, json.loads(public.read_text()), key
