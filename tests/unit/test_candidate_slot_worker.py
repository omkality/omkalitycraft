import hashlib
import json

import pytest

from omk import candidate_slot_worker as worker
from omk.cold_backup_worker import digest


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


def test_readonly_proof_binds_ports_runtime_receipt_and_artifacts(inputs):
    request, source, storage, root, _, receipt = inputs
    before = {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }
    value = worker.execute(request, source, storage, root)
    assert value["runtime_receipt_sha256"] == digest(receipt) and value[
        "binding_sha256"
    ] == digest(request["binding"])
    assert before == {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize(
    "change",
    [
        "offline",
        "rcon",
        "game-port",
        "rcon-port",
        "server-ip",
        "duplicate",
        "forge",
        "agent",
        "logging",
        "template",
    ],
)
def test_bad_launch_binding_or_pins_refused(inputs, change):
    request, source, storage, root, profiles, _ = inputs
    path = root / "server.properties"
    text = path.read_text()
    replacements = {
        "offline": ("online-mode=true", "online-mode=false"),
        "rcon": ("enable-rcon=true", "enable-rcon=false"),
        "game-port": ("server-port=25576", "server-port=25565"),
        "rcon-port": ("rcon.port=25575", "rcon.port=25574"),
        "server-ip": ("server-ip=", "server-ip=127.0.0.1"),
    }
    if change in replacements:
        path.write_text(text.replace(*replacements[change]))
    elif change == "duplicate":
        path.write_text(text + "server-port=25576\n")
    elif change == "template":
        (profiles / "forge112-server.json").write_text("{}")
    else:
        (
            root
            / {
                "forge": "forge.jar",
                "agent": ".omk/authlib-injector.jar",
                "logging": "libraries/log4j.jar",
            }[change]
        ).write_bytes(b"changed")
    with pytest.raises(ValueError):
        worker.execute(request, source, storage, root)
