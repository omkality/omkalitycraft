"""Test dependencies for launcher requirements."""

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from launcher.install import current_platform
from launcher.releases import read_release
from omk.distribution.publish import build_release


@pytest.fixture
def requirements(tmp_path):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    keys = {hashlib.sha256(public).hexdigest()[:16]: base64.b64encode(public).decode()}
    cdn = tmp_path / "cdn"
    directory = cdn / "releases/test" / current_platform()
    files = directory / "files"
    files.mkdir(parents=True)
    for name in ["java", "agent.jar", "forge.jar"]:
        (files / name).write_bytes(b"non-executable fixture")
    launch = {
        "java": "java",
        "agent": "agent.jar",
        "classpath": ["forge.jar"],
        "main_class": "net.minecraft.launchwrapper.Launch",
        "assets": "assets",
        "natives": "natives",
        "game_args": [],
    }

    def create(minimum):
        envelope = build_release(
            files,
            pack_id="test",
            version="1.0",
            minecraft="1.12.2",
            platform=current_platform(),
            launch=launch,
            key=key,
            minimum_launcher_version=minimum,
        )
        (directory / "manifest.json").write_text(json.dumps(envelope), encoding="utf-8")
        return read_release(json.dumps(envelope).encode(), keys)

    return create, cdn, key, keys
