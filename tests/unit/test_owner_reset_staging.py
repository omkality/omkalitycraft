import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    admin_reset_staging as owner,
    owner_volumes,
)
from omk.admin import AdminError, _write_private
from omk.cli import main
from omk.cold_backup_worker import digest
from tests.unit.test_owner_maintenance import (
    flow as maintenance_flow,
    stop_and_backup,
)
from tests.unit.test_owner_restores import (
    targets as restore_targets,
    write_targets,
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


def test_recorded_plan_blocks_resume_and_cancel_until_explicit_abandon(controller):
    cfg, flow, window, backup, state, _ = controller
    op = plan(controller)
    before = maintenance.read_record(cfg, window)
    assert owner.execute(cfg, op, "status")["stage"] == "planned"
    for action in ("start", "cancel"):
        with pytest.raises(AdminError, match="candidate is pending"):
            maintenance.execute(
                cfg, window, action, backup_operation=backup["operation"]
            )
    assert before == maintenance.read_record(cfg, window)
    assert "start" not in flow[-1]
    assert owner.execute(cfg, op, "stage", {})["stage"] == "staged"
    assert owner.execute(cfg, op, "verify")["ready_for_start"] is False
    with pytest.raises(AdminError, match="attempted"):
        owner.execute(cfg, op, "stage", {})
    with pytest.raises(AdminError, match="candidate is pending"):
        maintenance.execute(cfg, window, "start", backup_operation=backup["operation"])
    assert owner.execute(cfg, op, "abandon")["stage"] == "abandoned"
    assert owner.execute(cfg, op, "abandon")["stage"] == "abandoned"
    assert state["complete"]  # Abandon retains the candidate; no delete or promotion.
    assert (
        maintenance.execute(cfg, window, "start", backup_operation=backup["operation"])[
            "stage"
        ]
        == "complete"
    )
    assert state["calls"] == ["plan", "stage", "verify"]


def test_cli_exposes_only_closed_candidate_workflow_and_safe_summary(
    controller, monkeypatch, capsys
):
    from omk import admin  # noqa: PLC0415

    cfg, _, window, backup, _, _ = controller
    monkeypatch.setattr(admin, "load_operator_config", lambda _: cfg)
    prefix = [
        "admin",
        "--config",
        str(cfg.private / "operator.toml"),
        "resource-resets",
    ]
    assert (
        main(
            [
                *prefix,
                "plan",
                "--server",
                "dj2",
                "--dimension",
                "-18000",
                "--maintenance-operation",
                window,
                "--backup-operation",
                backup["operation"],
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert not result["source_changes"] and not result["ready_for_start"]
    assert "expected" not in result and "runtime_sha256" not in result
    assert main([*prefix, "stage", "--operation", result["operation"]]) == 0
    assert json.loads(capsys.readouterr().out)["stage"] == "staged"
    assert "resource-resets:stage" in (cfg.private / "audit.jsonl").read_text()


def test_listing_recovers_operation_id_without_docker_and_hides_other_servers(
    controller, monkeypatch
):
    cfg, _, _, _, _, _ = controller
    op = plan(controller)

    def unavailable(*args, **kwargs):
        pytest.fail("Listing must not contact Docker or require a running service")

    monkeypatch.setattr(backups, "docker", unavailable)
    result = owner.list_operations(cfg, "dj2")
    assert [r["operation"] for r in result["operations"]] == [op]
    with pytest.raises(AdminError, match="allowlist"):
        owner.list_operations(cfg, "unknown")


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_lost_stage_outcome_recovers_by_readonly_verify_without_reextract(
    controller, monkeypatch, failure
):
    cfg, _, window, _, state, original = controller
    op = plan(controller)

    def lost(record, action):
        result = original(record, action)
        if action == "stage":
            raise failure("lost outcome")
        return result

    monkeypatch.setattr(owner, "worker", lost)
    with pytest.raises(AdminError if failure is OSError else KeyboardInterrupt):
        owner.execute(cfg, op, "stage", {})
    assert owner.read_record(cfg, op)["stage"] in {"staging", "incomplete"}
    with pytest.raises(AdminError):
        owner.require_clear(cfg, window)
    with pytest.raises(AdminError, match="attempted"):
        owner.execute(cfg, op, "stage", {})
    assert owner.execute(cfg, op, "verify")["stage"] == "staged"
    assert state["calls"].count("stage") == 1


def test_partial_stage_cannot_be_verified_or_repeated_but_can_be_retained_and_abandoned(
    controller, monkeypatch
):
    cfg, _, window, _, state, original = controller
    op = plan(controller)

    def partial(record, action):
        if action == "stage":
            state["partial"] = True
            raise OSError("partial write")
        return original(record, action)

    monkeypatch.setattr(owner, "worker", partial)
    with pytest.raises(AdminError, match="incomplete"):
        owner.execute(cfg, op, "stage", {})
    with pytest.raises(AdminError, match="receipt"):
        owner.execute(cfg, op, "verify")
    with pytest.raises(AdminError):
        owner.require_clear(cfg, window)
    owner.execute(cfg, op, "abandon")
    owner.require_clear(cfg, window)
    assert state["partial"] and state["complete"] is False


@pytest.mark.parametrize(
    "change",
    [
        "checkpoint",
        "destination",
        "target",
        "backup",
        "window",
        "ttl",
        "policy",
        "landing-policy",
    ],
)
def test_frozen_plan_refuses_changed_inputs_before_writing(
    controller, monkeypatch, change
):
    cfg, flow, window, backup, state, _ = controller
    op = plan(controller)
    if change == "checkpoint":
        flow[2]["finished"] = "changed-stop"
    elif change == "destination":
        state["destination"]["created"] = "replaced"
    elif change == "target":
        state["target"]["data_volume"] = "replacement"
    elif change == "backup":
        backup["source"]["runtime_sha256"] = "changed"
        backups.save(cfg, backup, "complete")
    elif change == "window":
        record = maintenance.read_record(cfg, window)
        record["runtime"]["runtime_sha256"] = "changed"
        maintenance.save(cfg, record, "stopped")
    elif change == "ttl":
        record = owner.read_record(cfg, op)
        record["created_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        owner.save(cfg, record, "planned")
    elif change == "policy":
        monkeypatch.setenv("OMK_BACKUP_MAX_COUNT", "13")
    else:
        monkeypatch.setenv("OMK_RESET_LANDING_RADIUS", "7")
    with pytest.raises(AdminError):
        owner.execute(
            cfg, op, "stage", None if change in {"policy", "landing-policy"} else {}
        )
    assert state["calls"] == ["plan"] and state["complete"] is False


@pytest.mark.parametrize("dimension", [0, -1, 1, 2, -18001, True])
def test_only_explicit_dimension_is_allowed(controller, dimension):
    cfg, _, window, backup, state, _ = controller
    with pytest.raises(AdminError, match="allowlist"):
        owner.plan(cfg, "dj2", dimension, window, backup["operation"], {})
    assert state["calls"] == []


def test_backup_runtime_must_match_clean_maintenance_runtime(controller):
    cfg, _, window, backup, state, _ = controller
    backup["source"]["runtime_sha256"] = "changed-runtime"
    backups.save(cfg, backup, "complete")
    with pytest.raises(AdminError, match="runtime changed"):
        owner.plan(cfg, "dj2", -18000, window, backup["operation"], {})
    assert state["calls"] == []


def test_second_active_plan_is_refused_and_abandoned_target_is_not_deleted(controller):
    cfg, _, _, _, state, _ = controller
    op = plan(controller)
    with pytest.raises(AdminError, match="existing resource"):
        plan(controller)
    owner.execute(cfg, op, "abandon")
    second = plan(controller)
    assert second != op and state["calls"] == ["plan", "plan"]


def test_corrupt_private_journal_blocks_maintenance_without_echoing_payload(controller):
    cfg, _, window, backup, _, _ = controller
    folder = cfg.private / "resource-resets"
    folder.mkdir()
    _write_private(
        folder / ("a" * 32 + ".json"), cfg.private, {"api_token": "private-payload"}
    )
    with pytest.raises(AdminError) as error:
        maintenance.execute(cfg, window, "start", backup_operation=backup["operation"])
    assert "private-payload" not in str(error.value)


def test_active_or_stopped_target_binding_blocks_abandon(controller, monkeypatch):
    cfg, _, window, _, _, _ = controller
    op = plan(controller)

    def busy(*a, **kwargs):
        assert kwargs["unused"] is True
        raise AdminError("A helper still references target")

    monkeypatch.setattr(owner_volumes, "destination", busy)
    with pytest.raises(AdminError, match="helper"):
        owner.execute(cfg, op, "abandon")
    with pytest.raises(AdminError):
        owner.require_clear(cfg, window)


@pytest.fixture
def targets(tmp_path):
    cfg, source, restore = restore_targets.__wrapped__(tmp_path)
    reset = {**restore, "data_volume": "reset-candidate", "dimension": -18000}
    write_targets(cfg, "resource-resets.toml", {"dj2": reset})
    return cfg, source, restore, reset


def test_shared_inventory_accepts_distinct_targets_and_diagnostic_only_peer(
    targets, tmp_path
):
    cfg, source, restore, reset = targets
    cfg = replace(cfg, servers={**cfg.servers, "diagnostics": tmp_path / "other"})
    assert owner_volumes.target_for(cfg, "dj2", source, "resource-resets.toml") == reset
    assert owner_volumes.target_for(cfg, "dj2", source, "restores.toml") == restore


@pytest.mark.parametrize("alias", ["source", "store", "restore"])
def test_reset_target_cannot_alias_any_other_workflow(targets, alias):
    cfg, source, restore, reset = targets
    reset["data_volume"] = {
        "source": source["data_volume"],
        "store": source["store_volume"],
        "restore": restore["data_volume"],
    }[alias]
    write_targets(cfg, "resource-resets.toml", {"dj2": reset})
    for filename in ("restores.toml", "resource-resets.toml"):
        with pytest.raises(AdminError, match="distinct"):
            owner_volumes.target_for(cfg, "dj2", source, filename)


@pytest.mark.parametrize("bad", [0, -1, 2, True, "-18000"])
def test_dimension_config_is_strict_and_reserved_dimensions_are_refused(targets, bad):
    cfg, source, _, reset = targets
    # JSON syntax for the deliberately invalid scalar is also valid TOML here.
    reset["dimension"] = bad
    write_targets(cfg, "resource-resets.toml", {"dj2": reset})
    with pytest.raises(AdminError):
        owner_volumes.target_for(cfg, "dj2", source, "resource-resets.toml")


@pytest.mark.parametrize("action", ["plan", "stage", "verify"])
def test_worker_mounts_source_and_backup_readonly_and_only_stage_can_write_target(
    monkeypatch, action
):
    captured = []
    policy = backups.settings({})
    record = {
        "operation": "a" * 32,
        "source": {"data_volume": "source", "store_volume": "store", "world": "world"},
        "target": {"data_volume": "candidate"},
        "dimension": -18000,
        "settings": policy,
        "snapshot": "snapshot-" + "b" * 32,
        "preflight_options": {"landing_radius": 7},
        "expected": {"frozen": True},
    }
    monkeypatch.setattr(backups, "volume", lambda *a: {})
    monkeypatch.setattr(owner_volumes, "destination", lambda *a, **kw: {})

    def docker(*args, **kwargs):
        captured.append(args)
        request = json.loads(kwargs["stdin"])
        assert request["preflight_options"] == record["preflight_options"]
        if action == "plan":
            result = {
                k: request[k] for k in ("operation", "world", "dimension", "snapshot")
            }
            result.update(
                ready_for_start=False, preflight={"policy": record["preflight_options"]}
            )
        else:
            result = {
                "operation": record["operation"],
                "staged": True,
                "promoted": False,
                "ready_for_start": False,
                "plan_sha256": digest(record["expected"]),
            }
        return json.dumps({"ok": True, "result": result})

    monkeypatch.setattr(backups, "docker", docker)
    owner.worker(record, action)
    args = captured[0]
    assert "type=volume,source=source,target=/server,readonly" in args
    assert "type=volume,source=store,target=/backup,readonly" in args
    assert (
        "type=volume,source=candidate,target=/target"
        + ("" if action == "stage" else ",readonly")
        in args
    )
    assert args[args.index("--network") + 1] == "none" and "--read-only" in args
    assert "no-new-privileges:true" in args and "docker.sock" not in " ".join(args)
