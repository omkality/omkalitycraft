import json
from datetime import UTC, datetime, timedelta

import pytest

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    admin_reset_staging as owner,
    owner_volumes,
)
from omk.admin import AdminError
from omk.cold_backup_worker import digest
from tests.unit.test_owner_reset_staging import (
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


def test_owner_runtime_plan_write_verify_still_requires_explicit_abandon(flow):
    setup, operation, _ = flow
    cfg, _, window, backup, state, _ = setup
    runtime_plan(flow)
    assert (
        owner.execute(cfg, operation, "runtime-stage", {})["stage"] == "runtime-ready"
    )
    status = owner.execute(cfg, operation, "runtime-verify", {})
    assert status["runtime_prepared"] is True and status["ready_for_start"] is False
    assert status["promoted"] is False and status["ready_for_players"] is False
    assert owner.list_operations(cfg, "dj2")["operations"] == [status]
    for action in ["start", "cancel"]:
        with pytest.raises(AdminError, match="pending"):
            maintenance.execute(
                cfg, window, action, backup_operation=backup["operation"]
            )
    with pytest.raises(AdminError, match="runtime-verify"):
        owner.execute(cfg, operation, "verify")
    for action in ["runtime-plan", "runtime-stage", "stage"]:
        with pytest.raises(AdminError):
            owner.execute(cfg, operation, action, {})
    assert owner.execute(cfg, operation, "abandon")["stage"] == "abandoned"
    assert state["runtime_complete"]
    assert (
        maintenance.execute(cfg, window, "start", backup_operation=backup["operation"])[
            "stage"
        ]
        == "complete"
    )


@pytest.mark.parametrize("error", [OSError, KeyboardInterrupt])
def test_lost_runtime_acknowledgement_verifies_without_second_write(
    flow, monkeypatch, error
):
    setup, operation, real = flow
    cfg = setup[0]
    runtime_plan(flow)

    def interrupted(record, action):
        result = real(record, action)
        if action == "runtime-stage":
            raise error("lost controller response")
        return result

    monkeypatch.setattr(owner, "worker", interrupted)
    with pytest.raises(KeyboardInterrupt if error is KeyboardInterrupt else AdminError):
        owner.execute(cfg, operation, "runtime-stage", {})
    assert owner.execute(cfg, operation, "status")["stage"] == (
        "runtime-writing" if error is KeyboardInterrupt else "runtime-incomplete"
    )
    with pytest.raises(AdminError):
        owner.execute(cfg, operation, "runtime-stage", {})
    assert owner.execute(cfg, operation, "runtime-verify")["stage"] == "runtime-ready"
    assert setup[4]["calls"].count("runtime-stage") == 1


def test_partial_runtime_remains_blocked_and_abandon_keeps_target(flow, monkeypatch):
    setup, operation, real = flow
    cfg = setup[0]
    runtime_plan(flow)

    def partial(record, action):
        if action == "runtime-stage":
            raise OSError("partial fixture")
        return real(record, action)

    monkeypatch.setattr(owner, "worker", partial)
    with pytest.raises(AdminError):
        owner.execute(cfg, operation, "runtime-stage", {})
    with pytest.raises(AdminError):
        owner.execute(cfg, operation, "runtime-verify")
    assert owner.execute(cfg, operation, "status")["stage"] == "runtime-incomplete"
    with pytest.raises(AdminError):
        maintenance.execute(cfg, setup[2], "cancel")
    assert owner.execute(cfg, operation, "abandon")["stage"] == "abandoned"


@pytest.mark.parametrize(
    "drift", ["ttl", "limits", "preflight", "destination", "checkpoint"]
)
def test_owner_rechecks_frozen_policy_lifecycle_and_ttl_before_runtime_write(
    flow, drift
):
    setup, operation, _ = flow
    cfg = setup[0]
    runtime_plan(flow)
    env = {}
    if drift == "ttl":
        r = owner.read_record(cfg, operation)
        r["runtime_created_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        owner.save(cfg, r, r["stage"])
    elif drift == "limits":
        env = {"OMK_BACKUP_HELPER_CPUS": "2"}
    elif drift == "preflight":
        env = {"OMK_RESET_LANDING_RADIUS": "7"}
    elif drift == "destination":
        setup[4]["destination"]["created"] = "changed"
    else:
        setup[1][2]["finished"] = "changed"
    calls = list(setup[4]["calls"])
    with pytest.raises(AdminError):
        owner.execute(cfg, operation, "runtime-stage", env)
    assert setup[4]["calls"] == calls and not setup[4]["runtime_complete"]


@pytest.mark.parametrize(
    "stage", ["planned", "incomplete", "abandoned", "runtime-planned"]
)
def test_runtime_plan_requires_completed_data_stage(flow, stage):
    setup, operation, _ = flow
    cfg = setup[0]
    r = owner.read_record(cfg, operation)
    owner.save(cfg, r, stage)
    with pytest.raises(AdminError):
        owner.execute(cfg, operation, "runtime-plan", {})


@pytest.mark.parametrize("action", ["runtime-plan", "runtime-stage", "runtime-verify"])
@pytest.mark.parametrize("wrong_identity", [False, True])
def test_runtime_worker_binding_mounts_and_redacted_receipt(
    monkeypatch, action, wrong_identity
):
    captured = []
    record = {
        "operation": "a" * 32,
        "source": {"data_volume": "source", "store_volume": "store", "world": "world"},
        "target": {"data_volume": "target"},
        "dimension": -18000,
        "snapshot": "snapshot-" + "b" * 32,
        "settings": backups.settings({}),
        "preflight_options": {},
        "expected": {"data": "sealed"},
        "runtime_expected": {"runtime": "sealed"},
    }
    monkeypatch.setattr(backups, "volume", lambda *a: None)
    monkeypatch.setattr(owner_volumes, "destination", lambda *a, **k: None)

    def docker(*args, **kwargs):
        captured.append(args)
        request = json.loads(kwargs["stdin"])
        assert request["expected"] == record["expected"]
        assert ("runtime_expected" in request) == (action != "runtime-plan")
        result = {
            "operation": record["operation"],
            "ready_for_start": False,
            "ready_for_players": False,
        }
        if action == "runtime-plan":
            result["data_plan_sha256"] = digest(record["expected"])
        else:
            result.update(
                runtime_plan_sha256=digest(record["runtime_expected"]),
                runtime_prepared=True,
                promoted=False,
            )
        if wrong_identity:
            result["operation"] = "c" * 32
        return json.dumps({"ok": True, "result": result})

    monkeypatch.setattr(backups, "docker", docker)
    if wrong_identity:
        with pytest.raises(AdminError):
            owner.worker(record, action)
    else:
        owner.worker(record, action)
    args = captured[0]
    assert "omk.resource_reset_runtime" in args
    assert "type=volume,source=source,target=/server,readonly" in args
    assert "type=volume,source=store,target=/backup,readonly" in args
    assert (
        "type=volume,source=target,target=/target"
        + ("" if action == "runtime-stage" else ",readonly")
        in args
    )
    assert args[args.index("--network") + 1] == "none" and "--read-only" in args
    assert "no-new-privileges:true" in args
