"""Bounded synthetic action history and verified cold snapshot inputs."""

import json

import pytest

from omk.backups import cold_backup_worker as worker
from omk.owner import admin_backups
from tests.fixtures.unit.owner.chat_history import (
    ACTOR,
    BOOT,
    NEXT_BOOT,
    START,
    control,
)
from tests.fixtures.unit.owner.operator_commands import config as make_config


def _action(boot, sequence, second, action, *, name="OldNick", **change):
    row = control(boot, "action", second)
    for field in ("dropped", "retention_days", "budget_bytes"):
        del row[field]
    return {
        **row,
        "sequence": sequence,
        "action": action,
        "actor": {"kind": "player", "uuid": ACTOR, "name": name},
        "dimension": 0,
        "x": 0,
        "y": 70,
        "z": 0,
        "registry": "minecraft:lever",
        "outcome": "accepted",
        **change,
    }


def _write(path, value):
    path.write_text(json.dumps(value), encoding="utf8")
    path.chmod(0o600)


def _segment(directory, boot, second, rows, tail=""):
    path = directory / f"action-{START + second * 1000:013d}-{boot}-000000001.jsonl"
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows) + tail, encoding="utf8"
    )
    path.chmod(0o600)


@pytest.fixture
def action_history(tmp_path):
    config, path = make_config(tmp_path, auth=False)
    directory = config.private / "action-history" / "dj2"
    directory.parent.mkdir(mode=0o700)
    directory.mkdir(mode=0o700)
    _segment(
        directory,
        BOOT,
        0,
        [
            control(BOOT, "start", 0),
            _action(BOOT, 1, 1, "activate"),
            _action(BOOT, 3, 2, "piston", actor={"kind": "automation"}, x=2),
            _action(BOOT, 4, 3, "sign_edit", text="PRIVATE_TEXT"),
            _action(BOOT, 5, 4, "activate", dimension=-1),
            control(BOOT, "checkpoint", 4, dropped=1),
        ],
        tail='{"partial":',
    )
    _segment(
        directory,
        NEXT_BOOT,
        8,
        [
            control(NEXT_BOOT, "start", 8),
            _action(NEXT_BOOT, 1, 9, "activate", name="NewNick"),
            _action(NEXT_BOOT, 2, 10, "activate", x=5000),
            control(NEXT_BOOT, "stop", 11),
        ],
    )
    return config, path


@pytest.fixture
def action_case(action_history, tmp_path):
    config, path = action_history
    root = tmp_path / "test-server"
    root.mkdir()
    (root / "server.properties").write_text("level-name=lab-world\n")
    world = root / "lab-world"
    world.mkdir()
    (world / "level.dat").write_bytes(b"test fixture before repair")
    storage = config.private / "test-snapshots"
    storage.mkdir(mode=0o700)
    settings = admin_backups.settings({"OMK_BACKUP_RESERVE_BYTES": "1048576"})
    operation = "c" * 32
    record = {
        "schema": 1,
        "operation": operation,
        "server": "dj2",
        "target": {"world": "lab-world", "release": "fixture"},
        "created_at": "2026-11-27T12:00:05.123456+00:00",
        "settings": settings,
        "history": [],
    }
    request = admin_backups.request_for(record, "plan")
    record["source"] = worker.source_summary(root, request)[1]
    request["source"] = record["source"]
    worker.prepare(root, storage, request)
    record["result"] = worker.publish(storage, request)
    source = storage / "store" / record["result"]["id"]
    source.chmod(0o700)
    for file in source.iterdir():
        file.chmod(0o600)
    (config.private / "backups").mkdir(mode=0o700)
    admin_backups.save(config, record, "complete")
    diagnostic = config.private / "stack.txt"
    diagnostic.write_text(
        "Description: Ticking block entity\njava.lang.IllegalArgumentException: PRIVATE_DETAIL\n"
        "\tat net.example.Fixture.tick(Fixture.java:24)\n",
        encoding="utf8",
    )
    diagnostic.chmod(0o600)
    _write(
        config.private / "incident.json",
        {
            "time": "2026-11-27T12:00:02.321Z",
            "dimension": 0,
            "position": [2, 70, 0],
            "kind": "minecraft_crash",
            "tps": 17.5,
            "mspt": 57,
            "diagnostic": "stack.txt",
        },
    )
    args = [
        "--evidence",
        "fixture-case",
        "--incident",
        "incident.json",
        "--backup-operation",
        operation,
        "--snapshot",
        str(source.relative_to(config.private)),
    ]
    return config, path, args, source, record
