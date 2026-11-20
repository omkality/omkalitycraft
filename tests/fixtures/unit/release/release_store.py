"""Test dependencies for release store."""

import json

import pytest

from omk.distribution.publish import build_release, signing_key


@pytest.fixture
def release(tmp_path):
    source = tmp_path / "files"
    (source / "runtime").mkdir(parents=True)
    for name in ["runtime/java", "agent.jar", "forge.jar", "locale.lang"]:
        (source / name).write_bytes(b"not executable, fixture only")
    keys_path = tmp_path / "public.json"
    key = signing_key(tmp_path / "offline.pem", keys_path)
    keys = json.loads(keys_path.read_bytes())

    def build(version="one"):
        return build_release(
            source,
            pack_id="fixture",
            version=version,
            minecraft="1.12.2",
            platform="windows-x64",
            key=key,
            launch={
                "java": "runtime/java",
                "agent": "agent.jar",
                "classpath": ["forge.jar"],
                "main_class": "net.minecraft.launchwrapper.Launch",
                "assets": "assets",
                "natives": "natives",
                "game_args": [],
            },
        )

    return source, keys, build
