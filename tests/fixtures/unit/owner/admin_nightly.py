"""Test dependencies for admin nightly."""

import copy

import pytest

from omk.backups.ftb_backup_policy import ADAPTER, SHA256
from omk.owner import admin_nightly as owner
from tests.fixtures.unit.owner.operator_commands import config


@pytest.fixture
def flow(tmp_path, monkeypatch):
    cfg, path = config(tmp_path)
    (cfg.private / "nightly.toml").write_text(
        f'schema=1\n[servers.dj2]\nadapter="{ADAPTER}"\n'
    )
    (cfg.private / "nightly.toml").chmod(0o600)
    state = {"running": True, "container": "a" * 64}
    target = {"container": "owned", "data_volume": "source", "store_volume": "store"}
    proof = {
        "adapter": ADAPTER,
        "artifact_sha256": SHA256,
        "config_sha256": "b" * 64,
        "runtime_sha256": "c" * 64,
        "stock_enabled_on_disk": False,
        "stock_shutdown_on_disk": False,
        "live_config_verified": False,
        "other_writers_verified": False,
    }
    calls = []
    monkeypatch.setattr(owner.backups, "target_for", lambda *a: copy.deepcopy(target))
    monkeypatch.setattr(owner.backups, "local_engine", lambda: None)
    monkeypatch.setattr(
        owner.maintenance, "binding", lambda *a: {"rcon_container_port": 25575}
    )
    monkeypatch.setattr(owner.maintenance, "snapshot", lambda *a: copy.deepcopy(state))

    def worker(record, action):
        assert action == "nightly-policy"
        assert record["target"] == target
        calls.append(action)
        return copy.deepcopy(proof)

    monkeypatch.setattr(owner.maintenance, "worker", worker)
    return cfg, path, state, proof, calls, worker
