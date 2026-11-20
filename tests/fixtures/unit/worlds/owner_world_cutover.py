"""Test dependencies for owner world cutover."""

import copy
import json

import pytest

from omk.backups.cold_backup_worker import digest
from omk.deployment import ingress
from omk.owner import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    admin_reset_staging as staging,
)
from omk.worlds import world_cutover as owner
from tests.fixtures.unit.worlds.owner_reset_runtime import (
    flow as runtime_flow,
    runtime_plan,
)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    base = runtime_flow.__wrapped__(tmp_path, monkeypatch)
    setup, operation, _ = base
    cfg, source_flow, window, backup, _data_state, _ = setup
    state = source_flow[1]
    runtime_plan(base)
    staging.execute(cfg, operation, "runtime-stage", {})
    gate = {"policy": {}, "proxy": "immutable"}
    observed = {"closed": True, "sessions": 0}
    monkeypatch.setattr(
        ingress, "capture", lambda *a, **kw: (copy.deepcopy(gate), dict(observed))
    )
    win = maintenance.read_record(cfg, window)
    win["ingress"] = gate
    maintenance.save(cfg, win, "stopped")
    p = staging.read_record(cfg, operation)
    p["maintenance_sha256"] = digest(maintenance.read_record(cfg, window))
    staging.save(cfg, p, "runtime-ready")
    docker = backups.docker

    def inspected(*args, **kw):
        if args[0] == "inspect":
            return json.dumps([{"Config": {"User": ""}}])
        if args[:2] == ("ps", "-aq"):
            return win["initial"]["container"]
        return docker(*args, **kw)

    monkeypatch.setattr(backups, "docker", inspected)
    filesystem = {"phase": "untouched", "writes": [], "lost": None}

    def work(config, record, resource, action):
        if action == "plan":
            return {
                "schema": 1,
                "operation": record["operation"],
                "world": "world",
                "test_identity": "frozen",
            }
        if action in {"apply", "recover", "revert"}:
            assert owner.read(cfg, record["operation"])["stage"] in {
                "applying",
                "reverting",
            }
            filesystem["writes"].append(action)
            filesystem["phase"] = "reverted" if action == "revert" else "installed"
            if filesystem["lost"] == action:
                filesystem["lost"] = None
                raise OSError("lost response after the filesystem action")
        if action == "cancel":
            assert owner.read(cfg, record["operation"])["stage"] == "cancelling"
            assert record["write_lease"] is None
            filesystem["phase"] = "cancelled"
        result = {
            "phase": filesystem["phase"],
            "identity_sha256": digest(record["expected"]),
            "old_world_retained": True,
            "ready_for_players": False,
            "server_started": False,
        }
        return result

    monkeypatch.setattr(owner, "worker", work)
    return cfg, state, window, backup, operation, filesystem, observed
