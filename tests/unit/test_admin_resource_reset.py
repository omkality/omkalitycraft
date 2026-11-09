import copy
import json
from unittest.mock import Mock

import pytest

from omk import admin_resource_reset as owner
from omk.admin import AdminError
from omk.cli import main
from omk.resource_reset_preflight import settings as preflight_settings
from tests.unit.test_operator_commands import config

TARGET = {
    "data_volume": "source",
    "store_volume": "store-not-mounted",
    "world": "world",
}


def test_preflight_cli_uses_owner_lock_and_validated_policy(
    controller, capsys, monkeypatch
):
    _settings, path, worker = controller
    monkeypatch.setenv("OMK_RESET_LANDING_RADIUS", "7")
    assert (
        main(
            [
                "admin",
                "--config",
                str(path),
                "resource-resets",
                "inspect",
                "--server",
                "dj2",
                "--dimension",
                "-18000",
                "--preflight",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["can_apply"] is False
    assert worker.call_args.kwargs["preflight_options"]["landing_radius"] == 7


def reply():
    return {
        "schema": 1,
        "adapter": "dj2-ftb5.4-jed1.6-inspection-v1",
        "world": "world",
        "resource_identity": {"dimension": "-18000"},
        "world_inventory_sha256": "a" * 64,
        "world_changes": False,
        "reset_plan": False,
        "can_apply": False,
        "backup_verified": False,
    }


@pytest.fixture
def controller(tmp_path, monkeypatch):
    settings, path = config(tmp_path)
    checkpoint = {"container": "owned-stopped-checkpoint"}
    monkeypatch.setattr(
        owner.backups, "target_for", Mock(return_value=copy.deepcopy(TARGET))
    )
    monkeypatch.setattr(owner.backups, "local_engine", Mock())
    monkeypatch.setattr(owner.backups, "checkpoint", Mock(return_value=checkpoint))
    fake_worker = Mock(return_value=reply())
    monkeypatch.setattr(owner, "worker", fake_worker)
    return settings, path, fake_worker


def test_cli_is_owner_only_inspection_and_audit_contains_no_world_payload(
    controller, capsys
):
    _settings, path, worker = controller
    assert (
        main(
            [
                "admin",
                "--config",
                str(path),
                "resource-resets",
                "inspect",
                "--server",
                "dj2",
                "--dimension",
                "-18000",
            ]
        )
        == 0
    )
    value = json.loads(capsys.readouterr().out)
    assert value["ok"] and not value["can_apply"] and not value["world_changes"]
    worker.assert_called_once()
    audit = json.loads((path.parent / "audit.jsonl").read_text())
    assert audit["operation"] == "resource-resets:inspect" and set(audit) == {
        "time",
        "operation",
        "ok",
    }


@pytest.mark.parametrize("action", ["apply", "wipe", "reset", "plan"])
def test_no_mutating_or_plan_action_is_exposed(controller, action):
    _settings, path, worker = controller
    with pytest.raises(SystemExit) as error:
        main(["admin", "--config", str(path), "resource-resets", action])
    assert error.value.code == 2
    worker.assert_not_called()


@pytest.mark.parametrize("dimension", [0, -1, -9, -9999])
def test_reserved_dimension_is_refused_before_docker_access(controller, dimension):
    settings, _path, worker = controller
    with pytest.raises(AdminError, match="allowlisted"):
        owner.inspect(settings, "dj2", dimension)
    worker.assert_not_called()
    owner.backups.checkpoint.assert_not_called()


def test_running_or_unowned_source_cannot_reach_worker(controller):
    settings, _path, worker = controller
    owner.backups.checkpoint.side_effect = AdminError("Source must be stopped")
    with pytest.raises(AdminError, match="stopped"):
        owner.inspect(settings, "dj2", -18000)
    worker.assert_not_called()


@pytest.mark.parametrize("drift", ["checkpoint", "configuration"])
def test_source_drift_discards_the_worker_result(controller, drift):
    settings, _path, _worker = controller
    if drift == "checkpoint":
        owner.backups.checkpoint.side_effect = [
            {"container": "before"},
            {"container": "after"},
        ]
    else:
        owner.backups.target_for.side_effect = [
            copy.deepcopy(TARGET),
            {**TARGET, "world": "other"},
        ]
    with pytest.raises(AdminError, match="changed"):
        owner.inspect(settings, "dj2", -18000)


def test_worker_is_networkless_readonly_and_never_mounts_store_or_docker_socket(
    monkeypatch,
):
    docker = Mock(return_value=json.dumps({"ok": True, "result": reply()}))
    monkeypatch.setattr(owner.backups, "docker", docker)
    settings = owner.backups.settings({"OMK_BACKUP_WORLD_MAX_BYTES": "123456"})
    assert owner.worker(TARGET, -18000, settings) == reply()
    args, kwargs = docker.call_args
    assert args[args.index("--network") + 1] == "none" and "--read-only" in args
    mounts = [args[i + 1] for i, value in enumerate(args) if value == "--mount"]
    assert all(v.endswith(",readonly") for v in mounts)
    assert any(v == "type=volume,source=source,target=/server,readonly" for v in mounts)
    assert all("store-not-mounted" not in v and "docker.sock" not in v for v in mounts)
    assert "--publish" not in args and "--privileged" not in args
    assert json.loads(kwargs["stdin"])["world_max_bytes"] == 123456


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "schema",
        "adapter",
        "policy",
        "dimension",
        "world_inventory_sha256",
        "world_changes",
        "ready_for_start",
        "portal_adapters_reviewed",
    ],
)
def test_preflight_worker_response_preserves_readonly_identity(monkeypatch, fault):
    options = preflight_settings({})
    value = reply()
    proof = {
        "schema": 1,
        "adapter": "dj2-2.23.4-forge112-reset-preflight-v1",
        "policy": options,
        "dimension": -18000,
        "world_inventory_sha256": value["world_inventory_sha256"],
        "world_changes": False,
        "ready_for_start": False,
        "portal_adapters_reviewed": False,
    }
    if fault:
        proof[fault] = "invalid"
    value["preflight"] = proof
    docker = Mock(return_value=json.dumps({"ok": True, "result": value}))
    monkeypatch.setattr(owner.backups, "docker", docker)
    if fault:
        with pytest.raises(AdminError, match="preflight"):
            owner.worker(
                TARGET, -18000, owner.backups.settings({}), preflight_options=options
            )
    else:
        assert (
            owner.worker(
                TARGET, -18000, owner.backups.settings({}), preflight_options=options
            )
            == value
        )
        query = json.loads(docker.call_args.kwargs["stdin"])
        assert query["action"] == "preflight" and query["options"] == options


@pytest.mark.parametrize(
    "change",
    ["can_apply", "world", "dimension", "adapter", "schema", "oversized", "error"],
)
def test_invalid_or_misrouted_worker_response_is_refused(monkeypatch, change):
    value = reply()
    if change == "can_apply":
        value["can_apply"] = True
    elif change == "dimension":
        value["resource_identity"]["dimension"] = "0"
    elif change == "oversized":
        value["extra"] = "x" * 65536
    else:
        value[change] = "different"
    response = (
        {"ok": True, "result": value}
        if change != "error"
        else {"ok": False, "error_type": "ValueError"}
    )
    monkeypatch.setattr(
        owner.backups, "docker", Mock(return_value=json.dumps(response))
    )
    with pytest.raises(AdminError):
        owner.worker(TARGET, -18000, owner.backups.settings({}))


@pytest.mark.parametrize("present", [False, True])
def test_interrupted_worker_only_removes_its_owned_helper(monkeypatch, present):
    calls = []
    identity = {}
    cid = "a" * 64

    def docker(*args, **_kwargs):
        calls.append(args)
        if args[0] == "run":
            identity["name"] = args[args.index("--name") + 1]
            identity["operation"] = args[args.index("--label") + 1].split("=", 1)[1]
            raise AdminError("Timed out")
        if args[0] == "ps":
            assert "name=^/" + identity["name"] + "$" in args
            assert "label=omkality.resource.inspection=" + identity["operation"] in args
            return cid if present else ""
        if args[0] == "inspect":
            return json.dumps(
                [
                    {
                        "Name": "/" + identity["name"],
                        "Config": {
                            "Labels": {
                                "omkality.resource.inspection": identity["operation"]
                            }
                        },
                    }
                ]
            )
        assert args == ("rm", "--force", cid)
        return cid

    monkeypatch.setattr(owner.backups, "docker", docker)
    with pytest.raises(AdminError, match="Timed out"):
        owner.worker(TARGET, -18000, owner.backups.settings({}))
    assert sum(c[0] == "rm" for c in calls) == int(present)


def test_changed_helper_identity_is_never_removed(monkeypatch):
    docker = Mock(
        side_effect=[
            "a" * 64,
            json.dumps([{"Name": "/other-helper", "Config": {"Labels": {}}}]),
        ]
    )
    monkeypatch.setattr(owner.backups, "docker", docker)
    with pytest.raises(AdminError, match="identity changed"):
        owner._cleanup_failed_worker("omk-resource-inspect-owned", "owned")
    assert all(call.args[0] != "rm" for call in docker.call_args_list)
