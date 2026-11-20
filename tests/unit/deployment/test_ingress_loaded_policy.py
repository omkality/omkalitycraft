import pytest

from omk.deployment import ingress
from omk.labs.recovery.recovery_console import ConsoleError
from omk.owner.admin import AdminError
from tests.fixtures.unit.deployment.ingress_loaded_policy import READY, flow

__all__ = ["READY", "flow"]


def test_open_freezes_disk_policy_and_loaded_boot_with_no_new_writer(flow):
    gate, state, calls, _path = flow
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    readiness = ingress.read(gate.cfg, op)["readiness"]
    assert readiness["backup_policy"] == {
        "disk": {k: v for k, v in state["disk"].items() if k != "runtime_sha256"},
        "loaded": state["loaded"],
    }
    assert calls == [
        "loaded",
        "operators",
        "disk",
        "operator-disk",
        "operators",
        "loaded",
    ]
    assert gate.writes == []
    assert ingress.execute(gate.cfg, op, "apply")["stage"] == "confirmed"
    assert gate.writes == ["open"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("automatic_backups_disabled", False),
        ("backup_running", True),
        ("backup_adapter", "unreviewed"),
        ("main_thread", False),
    ],
)
def test_unready_loaded_policy_never_creates_open_intent(flow, key, value):
    gate, state, calls, _path = flow
    state["loaded"][key] = value
    with pytest.raises(ConsoleError):
        ingress.plan(gate.cfg, "dj2", "open", {})
    assert "disk" not in calls and gate.writes == []
    assert ingress.records(gate.cfg) == []


@pytest.mark.parametrize("change", ["loaded", "disk", "bridge-boot"])
def test_late_policy_change_refuses_before_proxy_intent(flow, change):
    gate, state, _calls, _path = flow
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    if change == "loaded":
        state["loaded"]["backup_running"] = True
    elif change == "disk":
        state["disk"]["config_sha256"] = "f" * 64
    else:
        # Same Docker snapshot, different loaded bridge lifetime.
        state["loaded"]["boot"] = "b" * 32
    with pytest.raises((AdminError, ConsoleError)):
        ingress.execute(gate.cfg, op, "apply")
    assert gate.writes == [] and ingress.read(gate.cfg, op)["stage"] == "planned"


@pytest.mark.parametrize("change", ["loaded-boot", "backup", "docker-boot"])
def test_policy_during_disk_read_is_not_accepted(flow, change):
    gate, state, _calls, _path = flow

    def mutate():
        if change == "loaded-boot":
            state["loaded"]["boot"] = "b" * 32
        elif change == "backup":
            state["loaded"]["backup_running"] = True
        else:
            state["source"]["started"] = "new-boot"

    state["during_disk"] = mutate
    with pytest.raises((AdminError, ConsoleError)):
        ingress.plan(gate.cfg, "dj2", "open", {})
    assert gate.writes == [] and ingress.records(gate.cfg) == []


@pytest.mark.parametrize("change", ["missing", "artifact", "unexpected-field"])
def test_missing_owner_adapter_or_bad_disk_proof_refuses(flow, change):
    gate, state, _calls, path = flow
    if change == "missing":
        path.unlink()
    elif change == "artifact":
        state["disk"]["artifact_sha256"] = "f" * 64
    else:
        state["disk"]["ready_for_players"] = True
    with pytest.raises(AdminError):
        ingress.plan(gate.cfg, "dj2", "open", {})
    assert gate.writes == [] and ingress.records(gate.cfg) == []


def test_legacy_open_plan_is_readable_but_cannot_adopt_new_proof(flow):
    gate, _state, _calls, _path = flow
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    record = ingress.read(gate.cfg, op)
    record["readiness"].pop("backup_policy")
    ingress.save(gate.cfg, record, "planned")
    assert ingress.status(ingress.read(gate.cfg, op))["stage"] == "planned"
    with pytest.raises(AdminError, match="changed"):
        ingress.execute(gate.cfg, op, "apply")
    assert gate.writes == []
    assert ingress.execute(gate.cfg, op, "cancel")["stage"] == "cancelled"


def test_closing_remains_possible_without_any_backup_policy(flow):
    gate, state, calls, path = flow
    path.unlink()
    state["loaded"]["automatic_backups_disabled"] = False
    gate.state["runtime"]["closed"] = False
    op = ingress.plan(gate.cfg, "dj2", "closed", {})["operation"]
    assert ingress.execute(gate.cfg, op, "apply")["stage"] == "confirmed"
    assert gate.writes == ["close"] and calls == []


def test_generated_runtime_change_keeps_exact_backup_policy_binding(flow):
    gate, state, _calls, _path = flow
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    state["disk"]["runtime_sha256"] = "f" * 64
    assert ingress.execute(gate.cfg, op, "apply")["stage"] == "confirmed"
    assert gate.writes == ["open"]


def test_policy_change_after_open_keeps_intent_unconfirmed_until_reverified(
    flow, monkeypatch
):
    gate, state, _calls, _path = flow
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    original = ingress.worker

    def change_after_effect(config, value, action="status", **kwargs):
        result = original(config, value, action, **kwargs)
        if action == "open":
            state["loaded"]["backup_running"] = True
        return result

    monkeypatch.setattr(ingress, "worker", change_after_effect)
    with pytest.raises(ConsoleError):
        ingress.execute(gate.cfg, op, "apply")
    assert gate.writes == ["open"]
    assert ingress.read(gate.cfg, op)["stage"] == "applying"
    state["loaded"]["backup_running"] = False
    assert ingress.execute(gate.cfg, op, "verify")["stage"] == "confirmed"
    assert gate.writes == ["open"]
