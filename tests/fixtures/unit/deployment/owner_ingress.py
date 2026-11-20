"""Test dependencies for owner ingress."""

import copy
from types import SimpleNamespace

import pytest

from omk.deployment import ingress, ingress_template
from tests.fixtures.unit.owner.operator_commands import config
from tests.fixtures.unit.owner.owner_maintenance import flow as maintenance_flow


@pytest.fixture
def gate(tmp_path, monkeypatch):
    cfg, path = config(tmp_path)
    value = {
        "policy": ingress_template.settings({}),
        "proxy": {"id": "proxy-id", "source_id": "source-id", "started": "boot"},
        "config_sha256": "a" * 64,
    }
    runtime = {
        "closed": True,
        "sessions": 1,
        "address": "172.20.0.2",
        "backend_up": True,
        "config_sha256": "a" * 64,
        "properties_sha256": None,
    }
    state = {
        "deployment": value,
        "runtime": runtime,
        "boot": "source-boot",
        "lose": False,
    }
    writes = []
    monkeypatch.setattr(
        ingress.deployment,
        "capture",
        lambda *a, **k: copy.deepcopy(state["deployment"]),
    )
    monkeypatch.setattr(ingress, "source_ready", lambda *a: {"boot": state["boot"]})
    monkeypatch.setattr(ingress, "backend_address", lambda *a: "172.20.0.2")

    def work(config, value, action="status", *, source_required=False, operation=None):
        if action != "status":
            # Intent has to be durable before sending the only write.
            assert ingress.read(config, operation)["stage"] == "applying"
            writes.append(action)
            runtime["closed"] = action == "close"
            if state["lose"]:
                state["lose"] = False
                raise OSError("injected lost acknowledgement")
        result = dict(runtime)
        result["properties_sha256"] = "b" * 64 if source_required else None
        return result

    monkeypatch.setattr(ingress, "worker", work)
    return SimpleNamespace(cfg=cfg, path=path, state=state, writes=writes)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    return maintenance_flow.__wrapped__(tmp_path, monkeypatch)
