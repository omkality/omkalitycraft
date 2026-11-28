import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from omk.backups import cold_backup_worker as worker
from omk.backups.backup_archive import validate_inventory
from omk.backups.backup_store import BackupStore
from omk.backups.stopped_world_backup import LAB_POLICY
from omk.cli import main
from omk.owner import admin_backups as owner
from omk.owner.admin import AdminError
from omk.owner.operation_windows import read_windows
from tests.fixtures.unit.backups.cold_backups import controller, fixture, stopped
from tests.fixtures.unit.owner.operator_commands import config

__all__ = ["fixture", "stopped"]


def test_prepare_does_not_publish_then_recover_acknowledge_are_idempotent(fixture):
    root, storage, request = fixture
    request["prepared"] = worker.prepare(root, storage, request)
    store = BackupStore(storage / "store", LAB_POLICY, path_policy="linux-server")
    assert store.inspect() == []
    result = worker.publish(storage, request)
    assert len(store.inspect()) == 1
    assert worker.recover(storage, request) == result
    request["result"] = result
    worker.acknowledge(storage, request)
    worker.acknowledge(storage, request)
    assert worker.inspect_store(storage, request) == store.inspect()


@pytest.mark.parametrize("change", ["world", "runtime", "interrupted"])
def test_changed_or_interrupted_preparation_cannot_publish(fixture, change):
    root, storage, request = fixture
    if change == "world":
        (root / "world/level.dat").write_bytes(b"changed")
    elif change == "runtime":
        (root / "server.jar").write_bytes(b"changed")
    else:
        (storage / "incoming.zip").write_bytes(b"partial")
    with pytest.raises(ValueError):
        worker.prepare(root, storage, request)
    assert not (storage / "store").exists()


def test_recover_rejects_unpublished_or_wrong_archive(fixture):
    root, storage, request = fixture
    request["prepared"] = worker.prepare(root, storage, request)
    with pytest.raises(ValueError, match="unambiguous"):
        worker.recover(storage, request)
    worker.publish(storage, request)
    request["prepared"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="differs"):
        worker.recover(storage, request)


def test_acknowledgement_can_resume_after_partial_cleanup(fixture):
    root, storage, request = fixture
    request["prepared"] = worker.prepare(root, storage, request)
    request["result"] = worker.publish(storage, request)
    (storage / "incoming.zip").unlink()
    worker.acknowledge(storage, request)
    assert not any(
        (storage / name).exists()
        for name in ("incoming.zip", "prepared.json", "receipt.json")
    )


def test_cancel_only_unpublished_staging_preserves_history(fixture):
    root, storage, request = fixture
    request["prepared"] = worker.prepare(root, storage, request)
    assert worker.cancel(storage, request)["previous_history_unchanged"]
    worker.cancel(storage, request)
    assert worker.inspect_store(storage, request) == []


def test_cancel_cannot_erase_committed_snapshot_or_receipt(fixture):
    root, storage, request = fixture
    request["prepared"] = worker.prepare(root, storage, request)
    result = worker.publish(storage, request)
    with pytest.raises(ValueError, match="Publication may exist"):
        worker.cancel(storage, request)
    assert (storage / "store" / result["id"] / "archive.zip").exists()
    assert (storage / "receipt.json").exists()


def test_status_rejects_foreign_private_json_instead_of_printing_credentials(tmp_path):
    cfg, _ = config(tmp_path)
    operation = "a" * 32
    owner._write_private(
        owner.journal(cfg, operation), cfg.private, {"api_token": "secret-fixture"}
    )
    with pytest.raises(AdminError, match="journal"):
        owner.read_record(cfg, operation)


def test_expanded_limits_are_configurable_without_allocating_large_fixture():
    files = {"world/region/r.0.0.mca": {"bytes": 1024**3, "sha256": "a" * 64}}
    with pytest.raises(ValueError):
        validate_inventory(files)
    validate_inventory(files, max_expanded_bytes=2 * 1024**3)
    with pytest.raises(ValueError):
        validate_inventory(files, max_expanded_bytes=0)


@pytest.mark.parametrize("value", ["secret token", "-1", "0", "１２"])
def test_bad_environment_never_echoes_supplied_value(value):
    with pytest.raises(AdminError) as error:
        owner.settings({"OMK_BACKUP_MAX_BYTES": value})
    assert str(error.value) == "Invalid OMK_BACKUP_MAX_BYTES"


def test_target_requires_configured_server_and_pinned_image(tmp_path):
    cfg, _ = config(tmp_path)
    with pytest.raises(AdminError, match="allowlist"):
        owner.target_for(cfg, "other")


def test_two_servers_cannot_share_backup_volume(tmp_path):
    cfg, _ = config(tmp_path)
    cfg = replace(cfg, servers={**cfg.servers, "other": tmp_path / "other"})
    target = {
        "container": "source-a",
        "data_volume": "data-a",
        "store_volume": "store-a",
        "label": "omkality.test",
        "source_owner": "source-id",
        "store_owner": "store-id",
        "world": "world",
        "image": owner.IMAGE,
        "release": "fixture-v1",
    }
    other = {**target, "container": "source-b", "data_volume": "data-b"}
    text = "schema=1\n"
    for name, value in [("dj2", target), ("other", other)]:
        text += (
            "[servers."
            + name
            + "]\n"
            + "\n".join(key + "=" + json.dumps(val) for key, val in value.items())
            + "\n"
        )
    path = cfg.private / "backups.toml"
    path.write_text(text)
    path.chmod(0o600)
    with pytest.raises(AdminError, match="distinct"):
        owner.target_for(cfg, "dj2")


@pytest.mark.parametrize("bad", ["running", "oom", "fatal", "restart", "nested-mount"])
def test_checkpoint_refuses_unsafe_lifecycle(monkeypatch, bad):
    data = stopped()
    logs = "Stopping server\n"
    if bad == "running":
        data["State"]["Running"] = True
    if bad == "oom":
        data["State"]["OOMKilled"] = True
    if bad == "fatal":
        logs += "Encountered an unexpected exception\n"
    if bad == "restart":
        data["HostConfig"]["RestartPolicy"]["Name"] = "always"
    if bad == "nested-mount":
        data["Mounts"].append({"Destination": "/srv/world"})

    def docker(*args, **kwargs):
        if args[0] == "inspect":
            return json.dumps([data])
        if args[0] == "logs":
            return logs
        return ""

    monkeypatch.setattr(owner, "docker", docker)
    monkeypatch.setattr(owner, "volume", lambda *a: {})
    target = {
        "container": "source",
        "label": "omkality.test",
        "source_owner": "source-owner",
        "image": data["Config"]["Image"],
        "data_volume": "source-volume",
    }
    with pytest.raises(AdminError):
        owner.checkpoint(target)


def test_controller_never_publishes_if_source_restarts_after_prepare(
    tmp_path, monkeypatch
):
    cfg, _ = config(tmp_path)
    target = {"world": "world"}
    state = {"store": {}, "id": "original"}
    monkeypatch.setattr(owner, "target_for", lambda *a: target)
    monkeypatch.setattr(owner, "local_engine", lambda: None)
    monkeypatch.setattr(owner, "volume", lambda *a: {})
    monkeypatch.setattr(owner, "checkpoint", lambda *a: dict(state))
    actions = []

    def work(target, request):
        actions.append(request["action"])
        if request["action"] == "plan":
            return {"source": {}, "history": []}
        if request["action"] == "prepare":
            state["id"] = "restarted"
            return {"sha256": "a" * 64}
        pytest.fail("Must not publish after restart")

    monkeypatch.setattr(owner, "worker", work)
    record = owner.plan(cfg, "dj2", {})
    assert read_windows(cfg, "dj2", "cold_backup") is None
    times = iter([100, 112])
    monkeypatch.setattr(owner, "time", lambda: next(times))
    with pytest.raises(AdminError, match="incomplete"):
        owner.run(cfg, record["operation"], environment={})
    assert read_windows(cfg, "dj2", "cold_backup") == [[100, 112]]
    assert actions == ["plan", "prepare"]
    value = json.loads(owner.journal(cfg, record["operation"]).read_text())
    assert value["stage"] == "incomplete"
    with pytest.raises(AdminError):
        owner.run(cfg, record["operation"], environment={})
    assert read_windows(cfg, "dj2", "cold_backup") == [[100, 112]]


@pytest.mark.parametrize("change", ["expired", "policy", "target"])
def test_changed_plan_refuses_before_preparing(fixture, tmp_path, monkeypatch, change):
    cfg, _, _, _, target = controller(fixture, tmp_path, monkeypatch)
    record = owner.plan(cfg, "dj2", {})
    environment = {}
    if change == "expired":
        record["created_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        owner.save(cfg, record, "planned")
    elif change == "policy":
        environment = {"OMK_BACKUP_MAX_COUNT": "3"}
    else:
        target["world"] = "other"
    monkeypatch.setattr(
        owner, "worker", lambda *a: pytest.fail("Preparation attempted")
    )
    with pytest.raises(AdminError):
        owner.run(cfg, record["operation"], environment=environment)


def test_lost_host_journal_write_after_publish_is_reconciled_once(
    fixture, tmp_path, monkeypatch
):
    cfg, _, _, storage, _ = controller(fixture, tmp_path, monkeypatch)
    record = owner.plan(cfg, "dj2", {})
    times = iter([100, 127, 200, 208])
    monkeypatch.setattr(owner, "time", lambda: next(times))
    original = owner.save

    def disk_failure(config, value, stage):
        if stage == "published":
            raise OSError("private-disk-error")
        return original(config, value, stage)

    monkeypatch.setattr(owner, "save", disk_failure)
    with pytest.raises(OSError):
        owner.run(cfg, record["operation"], environment={})
    persisted = owner._read_json(owner.journal(cfg, record["operation"]), cfg.private)
    assert persisted["stage"] == "publishing"
    monkeypatch.setattr(owner, "save", original)
    result = owner.run(cfg, record["operation"], finish=True, environment={})
    assert result["snapshot"]["sequence"] == 1
    assert read_windows(cfg, "dj2", "cold_backup") == [[100, 127], [200, 208]]
    assert (
        len(
            BackupStore(
                storage / "store",
                LAB_POLICY,
                max_expanded_bytes=16 * 1024**3,
                path_policy="linux-server",
            ).inspect()
        )
        == 1
    )


def test_plan_cli_exposes_hashes_without_runtime_secrets(
    fixture, tmp_path, monkeypatch, capsys
):
    _cfg, path, root, _, _ = controller(fixture, tmp_path, monkeypatch)
    (root / "server.properties").write_text("rcon.password=private-fixture-secret")
    assert (
        main(["admin", "--config", str(path), "backups", "plan", "--server", "dj2"])
        == 0
    )
    output = capsys.readouterr()
    assert "private-fixture-secret" not in output.out + output.err
    value = json.loads(output.out)
    assert value["stage"] == "planned" and len(value["source"]["runtime_sha256"]) == 64
