"""Test dependencies for owner reset staging."""

import copy

import pytest

from omk.backups.cold_backup_worker import digest
from omk.owner import admin_reset_staging as owner
from omk.owner.admin import AdminError
from omk.owner.panels import owner_volumes
from tests.fixtures.unit.backups.owner_restores import (
    targets as restore_targets,
    write_targets,
)
from tests.fixtures.unit.owner.owner_maintenance import (
    flow as maintenance_flow,
    stop_and_backup,
)


@pytest.fixture
def controller(tmp_path, monkeypatch):
    flow = maintenance_flow.__wrapped__(tmp_path, monkeypatch)
    window, backup = stop_and_backup(flow)
    cfg, _source_state, _point, _calls = flow
    target = {"data_volume": "candidate", "dimension": -18000}
    state = {
        "destination": {"volume": "candidate", "created": "fresh", "owner": "owned"},
        "calls": [],
        "complete": False,
        "target": target,
    }
    monkeypatch.setattr(owner_volumes, "target_for", lambda *a: dict(target))
    monkeypatch.setattr(
        owner_volumes, "destination", lambda *a, **k: dict(state["destination"])
    )

    def worker(record, action):
        state["calls"].append(action)
        if action == "plan":
            return {
                "schema": 1,
                "operation": record["operation"],
                "snapshot": backup["result"]["id"],
                "source": copy.deepcopy(backup["source"]),
                "archive_sha256": backup["result"]["sha256"],
                "position": [8, 241, 8],
                "retained_files": 5,
                "omitted_files": 2,
                "changed_files": 2,
                "preflight": {"policy": dict(record["preflight_options"])},
                "ready_for_start": False,
            }
        if action == "stage":
            state["complete"] = True
        elif not state["complete"]:
            raise AdminError("No complete receipt")
        return {
            "operation": record["operation"],
            "staged": True,
            "promoted": False,
            "ready_for_start": False,
            "plan_sha256": digest(record["expected"]),
        }

    monkeypatch.setattr(owner, "worker", worker)
    return cfg, flow, window, backup, state, worker


def plan(controller):
    cfg, _, window, backup, _, _ = controller
    return owner.plan(cfg, "dj2", -18000, window, backup["operation"], {})["operation"]


@pytest.fixture
def targets(tmp_path):
    cfg, source, restore = restore_targets.__wrapped__(tmp_path)
    reset = {**restore, "data_volume": "reset-candidate", "dimension": -18000}
    write_targets(cfg, "resource-resets.toml", {"dj2": reset})
    return cfg, source, restore, reset
