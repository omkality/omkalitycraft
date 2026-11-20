"""Test dependencies for candidate slot worker."""

import hashlib
import json

import pytest

from omk.deployment import candidate_slot_worker as worker


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    root = tmp_path / "target"
    root.mkdir()
    (root / "server.properties").write_text(
        "server-port=25576\nrcon.port=25575\nenable-rcon=true\nonline-mode=true\nserver-ip=\n"
    )
    source, storage = tmp_path / "source", tmp_path / "store"
    source.mkdir()
    storage.mkdir()
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    monkeypatch.setattr(worker, "PROFILE_ROOT", profiles)
    receipts = {"operation": "a" * 32, "runtime_prepared": True}
    monkeypatch.setattr(
        worker.resource_reset_runtime, "execute", lambda request, *a: receipts
    )

    def artifact(name):
        path = root / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(name.encode())
        return {"path": name, "sha256": hashlib.sha256(name.encode()).hexdigest()}

    profile = {
        "forge": artifact("forge.jar"),
        "agent": artifact(".omk/authlib-injector.jar"),
    }
    logging = {"artifacts": [artifact("libraries/log4j.jar")]}
    a = json.dumps(profile).encode()
    b = json.dumps(logging).encode()
    (profiles / "forge112-server.json").write_bytes(a)
    (profiles / "log4j-java8.json").write_bytes(b)
    request = {
        "runtime": {"expected": "delegated-cold-proof"},
        "binding": {
            "game_container_port": 25576,
            "rcon_container_port": 25575,
            "template_sha256": hashlib.sha256(a).hexdigest(),
            "logging_sha256": hashlib.sha256(b).hexdigest(),
        },
    }
    return request, source, storage, root, profiles, receipts
