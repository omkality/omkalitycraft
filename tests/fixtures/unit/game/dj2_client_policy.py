"""Test dependencies for dj2 client policy."""

import hashlib

import pytest


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    jar = tmp_path / "UniversalTweaks-1.12.2-1.20.0.jar"
    jar.write_bytes(b"controlled artifact fixture")
    monkeypatch.setattr(
        "omk.game.policies.dj2_client_policy.LOAD_SOUND_ARTIFACT_SHA256",
        hashlib.sha256(jar.read_bytes()).hexdigest(),
    )
    return jar
