"""Test dependencies for owner reset runtime."""

import pytest

from omk.backups.cold_backup_worker import digest
from omk.owner import admin_reset_staging as owner
from omk.owner.admin import AdminError
from tests.fixtures.unit.worlds.owner_reset_staging import (
    controller as data_controller,
    plan,
)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    setup = data_controller.__wrapped__(tmp_path, monkeypatch)
    cfg, _, _, _, state, data_worker = setup
    operation = plan(setup)
    owner.execute(cfg, operation, "stage", {})
    state["runtime_complete"] = False

    def worker(record, action):
        if not action.startswith("runtime-"):
            return data_worker(record, action)
        state["calls"].append(action)
        if action == "runtime-plan":
            return {
                "data_plan_sha256": digest(record["expected"]),
                "runtime_files": 9,
                "runtime_bytes": 1234,
                "ready_for_start": False,
                "ready_for_players": False,
            }
        if action == "runtime-stage":
            state["runtime_complete"] = True
        if not state["runtime_complete"]:
            raise AdminError("Incomplete runtime fixture")
        return {
            "operation": record["operation"],
            "runtime_plan_sha256": digest(record["runtime_expected"]),
            "runtime_prepared": True,
            "promoted": False,
            "ready_for_start": False,
            "ready_for_players": False,
        }

    monkeypatch.setattr(owner, "worker", worker)
    return setup, operation, worker


def runtime_plan(flow):
    setup, operation, _ = flow
    assert (
        owner.execute(setup[0], operation, "runtime-plan", {})["stage"]
        == "runtime-planned"
    )
    return operation
