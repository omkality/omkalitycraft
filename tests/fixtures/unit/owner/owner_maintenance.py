"""Test dependencies for owner maintenance."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from omk.labs.recovery.recovery_console import ConsoleConfig
from omk.owner import (
    admin_backups as backups,
    admin_maintenance as owner,
)
from omk.owner.admin import _write_private
from tests.fixtures.unit.backups.cold_backups import fixture as cold_fixture
from tests.fixtures.unit.owner.operator_commands import config


@pytest.fixture
def flow(tmp_path, monkeypatch):
    cfg, _ = config(tmp_path)
    cfg = replace(cfg, recovery_consoles={"dj2": ConsoleConfig(25577, "rcon.json")})
    (cfg.private / "maintenance.toml").write_text(
        "schema=1\n[servers.dj2]\nrcon_container_port=25575\n"
    )
    (cfg.private / "maintenance.toml").chmod(0o600)
    _write_private(
        cfg.private / "rcon.json", cfg.private, {"password": "private-credential-12345"}
    )
    target = {
        "container": "owned",
        "data_volume": "data",
        "store_volume": "store",
        "world": "world",
    }
    original = {
        "container": "a" * 64,
        "image": "image",
        "created": "create",
        "started": "old",
        "restart_count": 0,
        "source": {},
        "store": {},
        "running": True,
    }
    state = copy.deepcopy(original)
    point = {
        "container": "a" * 64,
        "started": "old",
        "finished": (datetime.now(UTC) - timedelta(seconds=60)).isoformat(),
        "source": {},
        "store": {},
    }
    actions = []
    monkeypatch.setattr(backups, "target_for", lambda *a: dict(target))
    monkeypatch.setattr(backups, "local_engine", lambda: None)
    monkeypatch.setattr(owner, "snapshot", lambda *a: copy.deepcopy(state))
    monkeypatch.setattr(backups, "checkpoint", lambda *a: copy.deepcopy(point))
    monkeypatch.setattr(owner.RecoveryConsole, "ready", lambda self: None)

    def worker(record, action, backup=None):
        actions.append(action)
        return (
            {"runtime_sha256": "a" * 64}
            if action == "runtime"
            else {"snapshot": backup["result"]}
        )

    def stop(*args):
        actions.append("stop")
        state["running"] = False

    def docker(*args, **kwargs):
        if args[0] == "start":
            actions.append("start")
            assert args[1] == original["container"]
            state.update(running=True, started=datetime.now(UTC).isoformat())
            return args[1]
        if args[0] == "logs":
            return 'Done (3.000s)! For help, type "help"'
        pytest.fail("Unexpected Docker call")

    monkeypatch.setattr(owner, "worker", worker)
    monkeypatch.setattr(owner, "console_stop", stop)
    monkeypatch.setattr(backups, "docker", docker)
    ticks = count(0, 10)
    monkeypatch.setattr(owner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(owner.time, "sleep", lambda seconds: None)
    return cfg, state, point, actions


def stop_and_backup(flow):
    cfg, _state, point, _actions = flow
    op = owner.plan(cfg, "dj2", {})["operation"]
    assert owner.execute(cfg, op, "stop", environment={})["stage"] == "stopped"
    record = owner.read_record(cfg, op)
    backup = {
        "schema": 1,
        "operation": "b" * 32,
        "stage": "complete",
        "server": "dj2",
        "target": record["target"],
        "operator_root": record["operator_root"],
        "checkpoint": copy.deepcopy(point),
        "source": {"runtime_sha256": "a" * 64},
        "settings": backups.settings({}),
        "result": {"id": "snapshot-" + "c" * 32, "sha256": "d" * 64},
    }
    (cfg.private / "backups").mkdir()
    backups.save(cfg, backup, "complete")
    return op, backup


@pytest.fixture
def data(tmp_path):
    return cold_fixture.__wrapped__(tmp_path)
