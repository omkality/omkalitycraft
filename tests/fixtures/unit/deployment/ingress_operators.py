"""Test dependencies for ingress operators."""

import copy

import pytest

from omk.deployment import ingress
from omk.labs.recovery.recovery_console import ConsoleError
from omk.owner.maintenance import maintenance_console
from tests.fixtures.unit.deployment.ingress_loaded_policy import flow as loaded_flow


@pytest.fixture
def flow(tmp_path, monkeypatch):
    gate, state, calls, path = loaded_flow.__wrapped__(tmp_path, monkeypatch)
    state["operators"] = {
        "schema": 1,
        "boot": "a" * 32,
        "main_thread": True,
        "operator_count": 0,
    }
    state["operator_disk"] = {"operators_sha256": "c" * 64, "operator_count": 0}
    state["during_operators"] = lambda: None
    original_worker = ingress.maintenance.worker

    def operators(self, *, boot):
        calls.append("operators")
        value = state["operators"]
        if value["operator_count"] != 0 or value["boot"] != boot:
            raise ConsoleError("Loaded operator list is not ready")
        return copy.deepcopy(value)

    def worker(record, action):
        if action != "operators":
            return original_worker(record, action)
        calls.append("operator-disk")
        state["during_operators"]()
        return copy.deepcopy(state["operator_disk"])

    monkeypatch.setattr(
        maintenance_console.MaintenanceConsole, "no_operators", operators, raising=False
    )
    monkeypatch.setattr(ingress.maintenance, "worker", worker)
    return gate, state, calls, path
