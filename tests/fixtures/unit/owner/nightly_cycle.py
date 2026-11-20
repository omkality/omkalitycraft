"""Test dependencies for nightly cycle."""

import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from omk.deployment import ingress
from omk.owner import (
    admin_backups as backups,
    admin_maintenance as maintenance,
)
from omk.owner.admin import AdminError
from omk.owner.maintenance import nightly_cycle as cycle
from tests.fixtures.unit.owner import owner_maintenance

maintenance_flow = owner_maintenance.flow


@pytest.fixture
def flow(maintenance_flow, monkeypatch):
    cfg, state, point, actions = maintenance_flow
    clock = {"value": datetime.now(UTC)}
    monkeypatch.setattr(cycle, "now", lambda: clock["value"])
    monkeypatch.setattr(
        cycle,
        "pause",
        lambda seconds: clock.update(value=clock["value"] + timedelta(seconds=seconds)),
    )
    env = {"OMK_NIGHTLY_WARNINGS_SECONDS": "5,1"}
    proof = {
        "adapter": "ftb-backups-1.1.0.1-disabled-v1",
        "artifact_sha256": "b" * 64,
        "config_sha256": "c" * 64,
        "runtime_sha256": "a" * 64,
        "stock_enabled_on_disk": False,
        "stock_shutdown_on_disk": False,
        "live_config_verified": False,
        "other_writers_verified": False,
    }
    monkeypatch.setattr(cycle.admin_nightly, "adapter", lambda *a: proof["adapter"])
    monkeypatch.setattr(
        cycle.admin_nightly, "inspect", lambda *a: {"disk_policy": copy.deepcopy(proof)}
    )
    old_worker = maintenance.worker
    monkeypatch.setattr(
        maintenance,
        "worker",
        lambda record, action, backup=None: (
            copy.deepcopy(proof)
            if action == "nightly-policy"
            else old_worker(record, action, backup)
        ),
    )
    deployment = {
        "policy": cycle.ingress_template.settings({}),
        "proxy": {"id": "proxy", "source_id": "a" * 64, "started": "proxy-boot"},
        "config_sha256": "c" * 64,
    }
    gate = {
        "closed": False,
        "sessions": 2,
        "address": "172.20.0.2",
        "backend_up": True,
        "config_sha256": "c" * 64,
        "properties_sha256": None,
    }
    monkeypatch.setattr(ingress.deployment, "configured", lambda c: True)
    monkeypatch.setattr(
        ingress.deployment, "capture", lambda *a, **kw: copy.deepcopy(deployment)
    )
    monkeypatch.setattr(ingress, "source_ready", lambda *a: copy.deepcopy(state))
    monkeypatch.setattr(ingress, "backend_address", lambda *a: "172.20.0.2")

    def gate_worker(
        config, value, action="status", *, source_required=False, operation=None
    ):
        if action != "status":
            assert ingress.read(config, operation)["stage"] == "applying"
            actions.append(action)
            gate["closed"] = action == "close"
        return {**gate, "properties_sha256": "b" * 64 if source_required else None}

    monkeypatch.setattr(ingress, "worker", gate_worker)
    budget = {
        "observed_within_limits": True,
        "declared_operation_limits": {"compatible": True},
        "categories": {"staging": {"charged_bytes": 0, "limit_bytes": 40 * 1024**3}},
        "filesystems": [{"available_bytes": 500 * 1024**3}],
    }
    monkeypatch.setattr(
        cycle.storage_estate,
        "inspect",
        lambda *a: {
            "budget": copy.deepcopy(budget),
            "resources": [
                {
                    "server": "dj2",
                    "role": "source",
                    "categories": {
                        "active_world": {
                            "apparent_bytes": 512,
                            "allocated_bytes": 4096,
                            "files": 1,
                        }
                    },
                }
            ],
        },
    )
    result = {
        "id": "snapshot-" + "c" * 32,
        "sha256": "b" * 64,
        "verified": True,
        "sequence": 1,
    }

    def backup_worker(target, request):
        action = request["action"]
        actions.append("backup-" + action)
        if action == "inspect":
            return {"history": []}
        if action == "plan":
            return {
                "history": [],
                "source": {
                    "runtime_sha256": "a" * 64,
                    "files": 1,
                    "expanded_bytes": 512,
                },
            }
        if action == "prepare":
            return {"sha256": "b" * 64}
        if action in {"publish", "recover"}:
            return copy.deepcopy(result)
        if action == "acknowledge":
            return {"acknowledged": True}
        pytest.fail("Unexpected backup action")

    monkeypatch.setattr(backups, "worker", backup_worker)
    monkeypatch.setattr(
        backups,
        "volume",
        lambda target, store=False: copy.deepcopy(
            point["store" if store else "source"]
        ),
    )
    sent = set()

    class Console:
        def ready(self, adapter, *, boot=None):
            actual = "d" * 32 if state["started"] == "old" else "e" * 32
            if boot is not None and actual != boot:
                raise AdminError("boot changed")
            return {
                "boot": actual,
                "backup_adapter": adapter,
                "automatic_backups_disabled": True,
                "backup_running": False,
                "main_thread": True,
                "schema": 1,
            }

        def warn(self, boot, operation, seconds):
            assert cycle.read(cfg, operation)["stage"] == "warning-requested"
            key = (boot, operation, seconds)
            actions.append("warn-replay" if key in sent else "warn-" + str(seconds))
            sent.add(key)

    console = Console()
    monkeypatch.setattr(cycle, "console", lambda *a: console)
    return SimpleNamespace(
        cfg=cfg,
        state=state,
        point=point,
        actions=actions,
        clock=clock,
        env=env,
        proof=proof,
        gate=gate,
        deployment=deployment,
        budget=budget,
        console=console,
        backup_worker=backup_worker,
        gate_worker=gate_worker,
    )
