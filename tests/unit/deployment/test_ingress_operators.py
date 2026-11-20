import json

import pytest

from omk.deployment import ingress
from omk.labs.recovery.recovery_console import ConsoleError
from omk.owner.admin import AdminError
from omk.owner.maintenance import maintenance_console
from tests.fixtures.unit.deployment.ingress_operators import flow

__all__ = ["flow"]


@pytest.mark.parametrize(
    "change", ["loaded-human", "loaded-service", "disk-only", "disk-invalid"]
)
def test_unsafe_operator_state_never_creates_open_plan(flow, change):
    gate, state, _calls, _ = flow
    if change.startswith("loaded-"):
        state["operators"]["operator_count"] = 1
    elif change == "disk-only":
        state["operator_disk"]["operator_count"] = 1
    else:
        state["operator_disk"]["extra"] = True
    with pytest.raises((AdminError, ConsoleError)):
        ingress.plan(gate.cfg, "dj2", "open", {})
    assert gate.writes == [] and ingress.records(gate.cfg) == []


def test_zero_loaded_and_disk_operators_are_frozen_without_new_writer(flow):
    gate, state, calls, _ = flow
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    proof = ingress.read(gate.cfg, op)["readiness"]["operator_policy"]
    assert proof == {"disk": state["operator_disk"], "loaded": state["operators"]}
    assert calls.count("operators") == 2 and calls.count("operator-disk") == 1
    assert gate.writes == []
    assert ingress.execute(gate.cfg, op, "apply")["stage"] == "confirmed"
    assert gate.writes == ["open"]


@pytest.mark.parametrize("change", ["loaded", "file", "boot"])
def test_operator_change_after_plan_refuses_before_intent(flow, change):
    gate, state, _, _ = flow
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    if change == "loaded":
        state["operators"]["operator_count"] = 1
    elif change == "file":
        state["operator_disk"]["operators_sha256"] = "f" * 64
    else:
        state["operators"]["boot"] = "b" * 32
    with pytest.raises((AdminError, ConsoleError)):
        ingress.execute(gate.cfg, op, "apply")
    assert gate.writes == [] and ingress.read(gate.cfg, op)["stage"] == "planned"


def test_loaded_operator_change_during_disk_read_is_rejected(flow):
    gate, state, _, _ = flow
    state["during_operators"] = lambda: state["operators"].update(operator_count=1)
    with pytest.raises(ConsoleError):
        ingress.plan(gate.cfg, "dj2", "open", {})
    assert gate.writes == [] and ingress.records(gate.cfg) == []


def test_old_open_plan_is_readable_but_needs_explicit_cancel(flow):
    gate, _, _, _ = flow
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    record = ingress.read(gate.cfg, op)
    record["readiness"].pop("operator_policy")
    ingress.journal(gate.cfg, op).write_text(json.dumps(record))
    assert ingress.read(gate.cfg, op)["stage"] == "planned"
    with pytest.raises(AdminError):
        ingress.execute(gate.cfg, op, "apply")
    assert gate.writes == []
    assert ingress.execute(gate.cfg, op, "cancel")["stage"] == "cancelled"


def test_closed_plan_and_cancel_do_not_need_operator_proof(flow, monkeypatch):
    gate, _, _, _ = flow
    monkeypatch.setattr(
        maintenance_console.MaintenanceConsole,
        "no_operators",
        lambda *a, **k: pytest.fail("unexpected operator query"),
    )
    op = ingress.plan(gate.cfg, "dj2", "closed", {})["operation"]
    assert ingress.execute(gate.cfg, op, "cancel")["stage"] == "cancelled"
