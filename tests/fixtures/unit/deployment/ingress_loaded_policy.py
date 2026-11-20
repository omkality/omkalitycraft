"""Test dependencies for ingress loaded policy."""

import copy
import json
from types import SimpleNamespace

import pytest

from omk.backups.ftb_backup_policy import ADAPTER, SHA256
from omk.deployment import ingress
from omk.labs.recovery.recovery_console import ConsoleConfig
from omk.owner import admin_nightly as nightly
from omk.owner.maintenance import maintenance_console
from tests.fixtures.unit.deployment.owner_ingress import gate as gate_fixture

READY = ingress.source_ready


@pytest.fixture
def flow(tmp_path, monkeypatch):
    gate = gate_fixture.__wrapped__(tmp_path, monkeypatch)
    monkeypatch.setattr(ingress, "source_ready", READY)
    cfg = gate.cfg
    path = cfg.private / "nightly.toml"
    path.write_text(f'schema=1\n[servers.dj2]\nadapter="{ADAPTER}"\n')
    path.chmod(0o600)
    target, binding = {"container": "source"}, {"rcon_container_port": 25575}
    gate.state["deployment"]["target"] = target
    state = {
        "source": {"container": "source-id", "running": True, "started": "boot"},
        "disk": {
            "adapter": ADAPTER,
            "artifact_sha256": SHA256,
            "config_sha256": "d" * 64,
            "runtime_sha256": "e" * 64,
            "stock_enabled_on_disk": False,
            "stock_shutdown_on_disk": False,
            "live_config_verified": False,
            "other_writers_verified": False,
        },
        "loaded": {
            "schema": 1,
            "boot": "a" * 32,
            "main_thread": True,
            "backup_adapter": ADAPTER,
            "automatic_backups_disabled": True,
            "backup_running": False,
        },
        "during_disk": lambda: None,
        "operators": {
            "schema": 1,
            "boot": "a" * 32,
            "main_thread": True,
            "operator_count": 0,
        },
        "operator_disk": {"operators_sha256": "c" * 64, "operator_count": 0},
    }
    calls = []
    monkeypatch.setattr(nightly.backups, "target_for", lambda *a: dict(target))
    monkeypatch.setattr(ingress.maintenance, "binding", lambda *a: dict(binding))
    monkeypatch.setattr(
        ingress.maintenance, "snapshot", lambda *a: copy.deepcopy(state["source"])
    )
    monkeypatch.setattr(
        ingress.maintenance,
        "credential",
        lambda *a: (ConsoleConfig(25575, "fixture.json"), "fixture-password-12345"),
    )
    monkeypatch.setattr(ingress.backups, "docker", lambda *a, **k: "Done (1.0s)!")
    monkeypatch.setattr(
        ingress, "RecoveryConsole", lambda *a: SimpleNamespace(ready=lambda: None)
    )

    def command(_config, _password, text):
        if text == "list omk-maintenance operators":
            calls.append("operators")
            return "OMK_MAINTENANCE_V1 " + json.dumps(state["operators"])
        assert text == "list omk-maintenance probe"
        calls.append("loaded")
        return "OMK_MAINTENANCE_V1 " + json.dumps(state["loaded"])

    def worker(record, action):
        if action == "operators":
            calls.append("operator-disk")
            return copy.deepcopy(state["operator_disk"])
        assert action == "nightly-policy" and record["target"] == target
        calls.append("disk")
        state["during_disk"]()
        return copy.deepcopy(state["disk"])

    monkeypatch.setattr(maintenance_console, "command", command)
    monkeypatch.setattr(nightly.maintenance, "worker", worker)
    return gate, state, calls, path
