import pytest

from omk.backups.cold_backup_worker import digest
from omk.deployment import candidate_slot_worker as worker
from tests.fixtures.unit.deployment.candidate_slot_worker import inputs

__all__ = ["inputs"]


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
