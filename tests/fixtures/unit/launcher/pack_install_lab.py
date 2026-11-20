"""Test dependencies for pack install lab."""

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from launcher.install import current_platform
from launcher.version import VERSION
from omk.distribution.publish import build_release


@pytest.fixture
def pack_releases(tmp_path):
    key = Ed25519PrivateKey.generate()
    # The same signer is sufficient here; the full DJ2 lab also verifies key rotation.
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    keys = {hashlib.sha256(public).hexdigest()[:16]: base64.b64encode(public).decode()}
    defaults = json.loads(
        Path("profiles/client-defaults/dj2.json").read_text(encoding="utf-8")
    )
    roots = []
    for version in ["old", "new"]:
        root = tmp_path / version
        files = root / "files"
        payload = {
            "runtime/bin/java": b"not an executable runtime",
            "agent.jar": b"not an executable agent",
            "forge.jar": b"not an executable loader",
            "mods/keep.jar": b"not an executable mod",
            f"mods/{version}.jar": version.encode() * (512 * 1024),
            "resourcepacks/FM_NewFont/pack.mcmeta": b'{"pack":{"pack_format":3}}',
            "resources/empty.txt": b"",
        }
        for name, data in payload.items():
            path = files / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        launch = {
            "java": "runtime/bin/java",
            "agent": "agent.jar",
            "classpath": ["forge.jar"],
            "main_class": "net.minecraft.launchwrapper.Launch",
            "assets": "assets",
            "natives": "natives",
            "game_args": ["--username", "{username}"],
            "client_defaults": {
                **{
                    k: v
                    for k, v in defaults.items()
                    if version != "old"
                    or k not in {"initial_options", "initial_keybindings"}
                },
                "servers": [
                    {"id": "omk-dj2", "name": version, "address": "127.0.0.1:25576"}
                ],
            },
        }
        envelope = build_release(
            files,
            pack_id="dj2",
            version=version,
            minecraft="1.12.2",
            platform=current_platform(),
            launch=launch,
            key=key,
            minimum_launcher_version=VERSION,
        )
        (root / "manifest.json").write_text(json.dumps(envelope), encoding="utf-8")
        roots.append(root)
    return roots, keys
