import copy
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from omk import (
    admin_maintenance as maintenance,
    ingress,
    ingress_template,
)
from omk.admin import AdminError
from omk.cli import main
from tests.unit.test_operator_commands import config
from tests.unit.test_owner_maintenance import flow as maintenance_flow


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


def test_open_close_and_cli_status_without_docker(gate, monkeypatch, capsys):
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    assert ingress.execute(gate.cfg, op, "apply")["stage"] == "confirmed"
    assert gate.writes == ["open"] and not gate.state["runtime"]["closed"]
    with pytest.raises(AdminError, match="attempted"):
        ingress.execute(gate.cfg, op, "apply")
    op = ingress.plan(gate.cfg, "dj2", "closed", {})["operation"]
    assert ingress.execute(gate.cfg, op, "apply")["stage"] == "confirmed"
    assert gate.writes == ["open", "close"] and gate.state["runtime"]["closed"]
    monkeypatch.setattr(
        ingress.deployment, "capture", lambda *a: pytest.fail("status called Docker")
    )
    assert (
        main(
            [
                "admin",
                "--config",
                str(gate.path),
                "ingress",
                "status",
                "--operation",
                op,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ready_for_players"] is False


@pytest.mark.parametrize("wanted", ["open", "closed"])
def test_lost_acknowledgement_verifies_without_repeating_write(gate, wanted):
    gate.state["runtime"]["closed"] = wanted == "open"
    op = ingress.plan(gate.cfg, "dj2", wanted, {})["operation"]
    gate.state["lose"] = True
    with pytest.raises(OSError, match="lost"):
        ingress.execute(gate.cfg, op, "apply")
    assert ingress.read(gate.cfg, op)["stage"] == "applying"
    with pytest.raises(AdminError, match="attempted"):
        ingress.execute(gate.cfg, op, "apply")
    assert ingress.execute(gate.cfg, op, "verify")["stage"] == "confirmed"
    assert gate.writes == ["open" if wanted == "open" else "close"]


@pytest.mark.parametrize("drift", ["config", "proxy", "source", "state", "expiry"])
def test_changed_plan_never_sends_a_write(gate, drift):
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    if drift == "config":
        gate.state["deployment"]["config_sha256"] = "c" * 64
    elif drift == "proxy":
        gate.state["deployment"]["proxy"]["started"] = "new-boot"
    elif drift == "source":
        gate.state["boot"] = "new-source-boot"
    elif drift == "state":
        gate.state["runtime"]["closed"] = False
    else:
        record = ingress.read(gate.cfg, op)
        record["created_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        ingress.save(gate.cfg, record, "planned")
    with pytest.raises(AdminError):
        ingress.execute(gate.cfg, op, "apply")
    assert gate.writes == [] and ingress.read(gate.cfg, op)["stage"] == "planned"


def test_proxy_restart_does_not_silently_reopen_or_repeat(gate):
    op = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    gate.state["lose"] = True
    with pytest.raises(OSError):
        ingress.execute(gate.cfg, op, "apply")
    gate.state["deployment"]["proxy"]["started"] = "new-boot"
    gate.state["runtime"]["closed"] = True
    with pytest.raises(AdminError, match="changed"):
        ingress.execute(gate.cfg, op, "verify")
    assert ingress.execute(gate.cfg, op, "cancel")["stage"] == "cancelled"
    assert gate.writes == ["open"]
    fresh = ingress.plan(gate.cfg, "dj2", "open", {})["operation"]
    assert ingress.execute(gate.cfg, fresh, "apply")["stage"] == "confirmed"


@pytest.mark.parametrize(
    "kind", ["maintenance", "resource-resets", "candidate-slot", "ingress"]
)
def test_pending_owner_work_blocks_opening_but_allows_closing(gate, monkeypatch, kind):
    if kind == "ingress":
        ingress.plan(gate.cfg, "dj2", "open", {})
    elif kind == "candidate-slot":
        monkeypatch.setattr(
            "omk.candidate_slots.records",
            lambda c: [{"server": "dj2", "stage": "running"}],
        )
    else:
        folder = gate.cfg.private / kind
        folder.mkdir()
        (folder / ("a" * 32 + ".json")).write_text("{}")
        reader = (
            "omk.admin_maintenance.read_record"
            if kind == "maintenance"
            else "omk.admin_reset_staging.read_record"
        )
        monkeypatch.setattr(reader, lambda *a: {"server": "dj2", "stage": "planned"})
    with pytest.raises(AdminError, match="pending"):
        ingress.plan(gate.cfg, "dj2", "open", {})
    closed = ingress.plan(gate.cfg, "dj2", "closed", {})["operation"]
    assert ingress.execute(gate.cfg, closed, "apply")["stage"] == "confirmed"
    assert gate.writes == ["close"]


def test_cancel_requires_closed_state_and_never_writes(gate):
    gate.state["runtime"]["closed"] = False
    op = ingress.plan(gate.cfg, "dj2", "closed", {})["operation"]
    with pytest.raises(AdminError, match="closed"):
        ingress.execute(gate.cfg, op, "cancel")
    gate.state["runtime"]["closed"] = True
    assert ingress.execute(gate.cfg, op, "cancel")["stage"] == "cancelled"
    assert gate.writes == []


@pytest.fixture
def flow(tmp_path, monkeypatch):
    return maintenance_flow.__wrapped__(tmp_path, monkeypatch)


def test_ingress_must_be_closed_before_stop_intent(flow, monkeypatch):
    cfg, state, _, actions = flow
    (cfg.private / "ingress.toml").write_text("configured")
    closed = [False]
    value = {"policy": {}, "proxy": "immutable"}

    def capture(*a, **kw):
        if kw.get("closed") and not closed[0]:
            raise AdminError("Close and confirm the ingress before maintenance")
        return value, {"closed": closed[0]}

    monkeypatch.setattr(ingress, "capture", capture)
    op = maintenance.plan(cfg, "dj2", {})["operation"]
    with pytest.raises(AdminError, match="Close"):
        maintenance.execute(cfg, op, "stop", environment={})
    assert maintenance.read_record(cfg, op)["stage"] == "planned"
    assert "stop" not in actions and state["running"]
    closed[0] = True
    assert maintenance.execute(cfg, op, "stop", environment={})["stage"] == "stopped"
    assert actions.count("stop") == 1


def test_new_ingress_definition_invalidates_old_maintenance_window(flow):
    cfg, _, _, actions = flow
    op = maintenance.plan(cfg, "dj2", {})["operation"]
    (cfg.private / "ingress.toml").write_text("appeared")
    with pytest.raises(AdminError, match="appeared"):
        maintenance.execute(cfg, op, "stop", environment={})
    assert "stop" not in actions
