import copy
import json
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    ingress,
    nightly_cycle as cycle,
    world_cutover,
)
from omk.admin import AdminError
from omk.cli import main
from omk.nightly_steps import child
from tests.unit import test_owner_maintenance

maintenance_flow = test_owner_maintenance.flow


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


def begin(flow):
    return cycle.prepare(flow.cfg, "dj2", flow.env)["operation"]


def reach(flow, operation, stage):
    for _ in range(100):
        if cycle.read(flow.cfg, operation)["stage"] == stage:
            return
        _result, wait = cycle.tick(flow.cfg, operation, flow.env)
        flow.clock["value"] += timedelta(seconds=wait)
    pytest.fail("Stage was not reached")


def test_one_cycle_uses_existing_controllers_and_explicit_child_ids(flow):
    operation = begin(flow)
    ids = cycle.read(flow.cfg, operation)["children"].copy()
    result = cycle.run(flow.cfg, operation=operation, environment=flow.env)
    assert result["stage"] == "complete" and result["children"] == ids
    for action in (
        "warn-5",
        "warn-1",
        "close",
        "stop",
        "backup-prepare",
        "backup-publish",
        "start",
        "open",
    ):
        assert flow.actions.count(action) == 1
    assert (
        flow.actions.index("warn-1")
        < flow.actions.index("close")
        < flow.actions.index("stop")
        < flow.actions.index("backup-publish")
        < flow.actions.index("start")
        < flow.actions.index("open")
    )
    assert not flow.gate["closed"] and flow.state["running"]
    assert (
        backups.read_record(flow.cfg, ids["backup"])["settings"]["reserve_bytes"]
        == 24 * 1024**3
    )
    before = flow.actions.copy()
    assert (
        cycle.run(flow.cfg, operation=operation, environment=flow.env)["stage"]
        == "complete"
    )
    assert flow.actions == before


@pytest.mark.parametrize(
    "edge",
    ["maintenance-plan", "close-plan", "close", "stop", "publish", "start", "open"],
)
def test_lost_acknowledgement_never_repeats_a_child_effect(flow, monkeypatch, edge):
    operation = begin(flow)
    if edge.endswith("plan"):
        target = maintenance if edge == "maintenance-plan" else ingress
        original = target.plan

        def lost(*args, **kw):
            original(*args, **kw)
            monkeypatch.setattr(target, "plan", original)
            raise KeyboardInterrupt

        monkeypatch.setattr(target, "plan", lost)
    elif edge in {"close", "open"}:
        original = ingress.worker

        def lost(*args, **kw):
            value = original(*args, **kw)
            if len(args) > 2 and args[2] == edge:
                monkeypatch.setattr(ingress, "worker", original)
                raise OSError("lost reply")
            return value

        monkeypatch.setattr(ingress, "worker", lost)
    elif edge == "stop":
        original = maintenance.console_stop

        def lost(*args):
            original(*args)
            monkeypatch.setattr(maintenance, "console_stop", original)
            raise KeyboardInterrupt

        monkeypatch.setattr(maintenance, "console_stop", lost)
    elif edge == "start":
        original = backups.docker

        def lost(*args, **kw):
            value = original(*args, **kw)
            if args[0] == "start":
                monkeypatch.setattr(backups, "docker", original)
                raise KeyboardInterrupt
            return value

        monkeypatch.setattr(backups, "docker", lost)
    else:
        original = backups.worker

        def lost(target, request):
            value = original(target, request)
            if request["action"] == "publish":
                monkeypatch.setattr(backups, "worker", original)
                raise OSError("lost publication reply")
            return value

        monkeypatch.setattr(backups, "worker", lost)
    with pytest.raises((KeyboardInterrupt, OSError, AdminError)):
        cycle.run(flow.cfg, operation=operation, environment=flow.env)
    assert (
        cycle.run(flow.cfg, operation=operation, environment=flow.env)["stage"]
        == "complete"
    )
    for action in (
        "close",
        "stop",
        "backup-prepare",
        "backup-publish",
        "start",
        "open",
    ):
        assert flow.actions.count(action) == 1


def test_warning_loss_reuses_same_game_notice(flow, monkeypatch):
    operation = begin(flow)
    original = flow.console.warn

    def lost(*args):
        original(*args)
        monkeypatch.setattr(flow.console, "warn", original)
        raise OSError("lost warning ack")

    monkeypatch.setattr(flow.console, "warn", lost)
    with pytest.raises(OSError):
        cycle.run(flow.cfg, operation=operation, environment=flow.env)
    assert cycle.read(flow.cfg, operation)["stage"] == "warning-requested"
    assert (
        cycle.run(flow.cfg, operation=operation, environment=flow.env)["stage"]
        == "complete"
    )
    assert flow.actions.count("warn-5") == 1 and flow.actions.count("warn-replay") == 1


@pytest.mark.parametrize("stage", ["created", "warnings", "closing", "stopping"])
def test_cancel_before_stop_never_reopens_or_stops_source(flow, stage):
    operation = begin(flow)
    reach(flow, operation, stage)
    assert cycle.cancel(flow.cfg, operation, flow.env)["stage"] == "cancelled"
    assert (
        flow.state["running"]
        and "stop" not in flow.actions
        and "open" not in flow.actions
    )
    assert flow.gate["closed"] == (stage == "stopping")
    assert (
        cycle.run(flow.cfg, operation=operation, environment=flow.env)["stage"]
        == "cancelled"
    )


def test_stale_countdown_after_close_can_cancel_without_late_stop(flow):
    operation = begin(flow)
    reach(flow, operation, "stopping")
    flow.clock["value"] += timedelta(hours=2)
    with pytest.raises(AdminError, match="stale"):
        cycle.tick(flow.cfg, operation, flow.env)
    assert "stop" not in flow.actions and flow.gate["closed"]
    assert cycle.cancel(flow.cfg, operation, flow.env)["stage"] == "cancelled"
    assert flow.gate["closed"] and flow.state["running"]


@pytest.mark.parametrize("kind", ["runtime", "source", "proxy", "policy", "budget"])
def test_drift_and_insufficient_storage_refuse_before_stop(flow, kind):
    operation = begin(flow)
    if kind == "runtime":
        flow.proof["runtime_sha256"] = "f" * 64
    elif kind == "source":
        flow.state["container"] = "replaced"
    elif kind == "proxy":
        flow.deployment["proxy"]["started"] = "restarted"
    elif kind == "policy":
        flow.env["OMK_BACKUP_MAX_COUNT"] = "3"
    else:
        flow.budget["observed_within_limits"] = False
    with pytest.raises(AdminError):
        cycle.run(flow.cfg, operation=operation, environment=flow.env)
    assert "stop" not in flow.actions and "backup-publish" not in flow.actions


def test_failed_prepare_leaves_original_offline_and_closed_without_repeating(
    flow, monkeypatch
):
    operation = begin(flow)
    original = backups.worker

    def failed(target, request):
        if request["action"] == "prepare":
            raise OSError("synthetic write refusal")
        return original(target, request)

    monkeypatch.setattr(backups, "worker", failed)
    with pytest.raises(AdminError):
        cycle.run(flow.cfg, operation=operation, environment=flow.env)
    assert flow.gate["closed"] and not flow.state["running"]
    assert "start" not in flow.actions and "open" not in flow.actions
    with pytest.raises(AdminError, match="no safe publication"):
        cycle.run(flow.cfg, operation=operation, environment=flow.env)


def test_second_active_cycle_and_closed_initial_service_refused(flow):
    begin(flow)
    with pytest.raises(AdminError, match="existing"):
        begin(flow)


def test_deliberately_closed_service_never_gets_implicit_open(flow):
    flow.gate["closed"] = True
    with pytest.raises(AdminError, match="already open"):
        begin(flow)
    assert "open" not in flow.actions and "stop" not in flow.actions


def test_wait_releases_owner_lock_and_cancel_does_not_require_old_environment(
    flow, monkeypatch
):
    operation = begin(flow)
    cancelled = []

    def pause(_seconds):
        # A separate operator/TUI process can cancel while the countdown waits.
        thread = threading.Thread(
            target=lambda: cancelled.append(cycle.cancel(flow.cfg, operation, {}))
        )
        thread.start()
        thread.join(3)
        assert not thread.is_alive()

    monkeypatch.setattr(cycle, "pause", pause)
    assert (
        cycle.run(flow.cfg, operation=operation, environment=flow.env)["stage"]
        == "cancelled"
    )
    assert len(cancelled) == 1 and flow.state["running"] and not flow.gate["closed"]
    assert "stop" not in flow.actions


@pytest.mark.parametrize("stage", ["closing", "stopping"])
def test_unattempted_close_can_be_abandoned_without_touching_proxy(flow, stage):
    operation = begin(flow)
    reach(flow, operation, stage)
    if stage == "closing":
        child(
            flow.cfg,
            cycle.read(flow.cfg, operation),
            "close",
            cycle.policy(flow.env)[1],
        )
    before = flow.actions.copy()
    cycle.cancel(flow.cfg, operation, flow.env)
    assert flow.actions == before
    assert flow.state["running"] and flow.gate["closed"] == (stage == "stopping")


@pytest.mark.parametrize("stage", ["warnings", "closing"])
def test_paused_countdown_never_closes_late(flow, stage):
    operation = begin(flow)
    reach(flow, operation, stage)
    flow.clock["value"] += timedelta(hours=2)
    with pytest.raises(AdminError, match=r"missed|expired|stale"):
        cycle.tick(flow.cfg, operation, flow.env)
    assert "close" not in flow.actions and "stop" not in flow.actions


def test_foreign_world_installation_cannot_be_adopted_by_backup_cycle(
    flow, monkeypatch
):
    operation = begin(flow)
    reach(flow, operation, "backing-up")
    monkeypatch.setattr(world_cutover, "for_window", lambda *a: {"operation": "f" * 32})
    with pytest.raises(AdminError, match="without world installation"):
        cycle.tick(flow.cfg, operation, flow.env)
    assert "backup-prepare" not in flow.actions and "start" not in flow.actions
    assert flow.gate["closed"] and not flow.state["running"]


def test_changed_backup_child_is_not_used_to_start_source(flow):
    operation = begin(flow)
    reach(flow, operation, "starting")
    parent = cycle.read(flow.cfg, operation)
    child = backups.read_record(flow.cfg, parent["children"]["backup"])
    child["source"]["runtime_sha256"] = "f" * 64
    backups.save(flow.cfg, child, "complete")
    with pytest.raises(AdminError, match="preallocated scope"):
        cycle.tick(flow.cfg, operation, flow.env)
    assert flow.gate["closed"] and "start" not in flow.actions


def test_failed_new_boot_policy_keeps_admission_closed(flow, monkeypatch):
    operation = begin(flow)
    reach(flow, operation, "starting")
    original = flow.console.ready

    def failed(*a, **kw):
        if flow.state["started"] != "old":
            raise AdminError("loaded policy is enabled")
        return original(*a, **kw)

    monkeypatch.setattr(flow.console, "ready", failed)
    with pytest.raises(AdminError, match="loaded policy"):
        cycle.tick(flow.cfg, operation, flow.env)
    assert flow.state["running"] and flow.gate["closed"] and "open" not in flow.actions
    monkeypatch.setattr(flow.console, "ready", original)
    assert (
        cycle.run(flow.cfg, operation=operation, environment=flow.env)["stage"]
        == "complete"
    )
    assert flow.actions.count("start") == 1


def test_cli_status_and_structured_failure_keep_recovery_identity(
    flow, monkeypatch, capsys
):
    operation = begin(flow)
    args = ["admin", "--config", str(flow.cfg.private / "operator.toml"), "nightly"]
    before = flow.actions.copy()
    assert main([*args, "status", "--operation", operation]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["operation"] == operation and not value["scheduler_enabled"]
    assert flow.actions == before

    def failed(*a, **kw):
        raise RuntimeError("potentially sensitive external detail")

    monkeypatch.setattr(cycle, "run", failed)
    assert main([*args, "run", "--operation", operation]) == 1
    captured = capsys.readouterr()
    value = json.loads(captured.out)
    assert (
        value["operation"] == operation
        and value["stage"] == "created"
        and not value["ok"]
    )
    assert "sensitive" not in captured.out and operation in captured.err


@pytest.mark.parametrize("raw", ["0", "61", "1.0", "-1", "999", "secret", "１"])
def test_invalid_grace_stops_before_any_owner_effect(flow, raw):
    with pytest.raises(AdminError, match="OMK_NIGHTLY_WARNING_GRACE_SECONDS"):
        cycle.prepare(
            flow.cfg, "dj2", {**flow.env, "OMK_NIGHTLY_WARNING_GRACE_SECONDS": raw}
        )
    assert not flow.actions


def test_countdown_wait_has_no_repeated_runtime_scan_but_due_notice_is_guarded(
    flow, monkeypatch
):
    operation = begin(flow)
    reach(flow, operation, "warnings")
    cycle.tick(flow.cfg, operation, flow.env)
    original = cycle.running

    def unexpected(*a, **kw):
        pytest.fail("No runtime scan is needed while just waiting")

    monkeypatch.setattr(cycle, "running", unexpected)
    _result, wait = cycle.tick(flow.cfg, operation, flow.env)
    assert wait == 4 and flow.actions.count("warn-5") == 1
    monkeypatch.setattr(cycle, "running", original)
    flow.clock["value"] += timedelta(seconds=4)
    flow.proof["runtime_sha256"] = "f" * 64
    with pytest.raises(AdminError, match="runtime"):
        cycle.tick(flow.cfg, operation, flow.env)
    assert "warn-1" not in flow.actions


@pytest.mark.parametrize(
    "field", ["runtime_sha256", "artifact_sha256", "config_sha256"]
)
def test_restart_allows_generated_runtime_writes_but_keeps_exact_stock_policy(
    flow, monkeypatch, field
):
    operation = begin(flow)
    reach(flow, operation, "starting")
    original = flow.console.ready

    def new_boot(*a, **kw):
        value = original(*a, **kw)
        if flow.state["started"] != "old":
            flow.proof[field] = "f" * 64
        return value

    monkeypatch.setattr(flow.console, "ready", new_boot)
    if field == "runtime_sha256":
        assert (
            cycle.run(flow.cfg, operation=operation, environment=flow.env)["stage"]
            == "complete"
        )
    else:
        with pytest.raises(AdminError, match="stock backup configuration"):
            cycle.tick(flow.cfg, operation, flow.env)
        assert flow.gate["closed"] and "open" not in flow.actions
