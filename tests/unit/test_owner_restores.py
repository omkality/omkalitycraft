import copy
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from omk import (
    admin_backups as backups,
    admin_restores as owner,
    owner_restore_worker as worker,
)
from omk.admin import AdminError
from omk.backup_store import BackupStore
from omk.stopped_world_backup import inventory
from tests.unit.test_linux_restore_policy import LIMITS, build
from tests.unit.test_operator_commands import config


@pytest.fixture
def data(tmp_path, monkeypatch):
    source, original, store, request, *_ = build(tmp_path, monkeypatch, "owner")
    storage = tmp_path / "backup"
    storage.mkdir()
    store.root.rename(storage / "store")
    store = BackupStore(storage / "store", LIMITS, path_policy="linux-server")
    files = inventory(source / "world", world_name="world", path_policy="linux-server")
    archive = tmp_path / "current.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        for name in files:
            out.write(source / name, name)
    store.publish(archive, files)
    target = tmp_path / "replacement"
    target.mkdir()
    for root in (source, target):
        (root / "server.jar").write_bytes(b"same-runtime")
    for name in ("server.properties", worker.policy.RANKS):
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((original / name).read_bytes())
    return copy.deepcopy(request), storage, target, source


def planned(data):
    request, storage, target, source = data
    expected = worker.execute({**request, "action": "plan"}, storage, target, source)
    return {**request, "expected": expected}, storage, target, source


def test_plan_is_readonly_and_complete_stage_can_be_reverified(data):
    request, storage, target, source = planned(data)
    assert not (target / worker.PLAN).exists()
    source_before = inventory(
        source / "world", world_name="world", path_policy="linux-server"
    )
    result = worker.execute({**request, "action": "apply"}, storage, target, source)
    assert result["staged"] and not result["promoted"]
    assert (
        worker.execute({**request, "action": "verify"}, storage, target, source)
        == result
    )
    assert (
        target / "world/player-progress.dat"
    ).read_bytes() == b"historical-inventory"
    assert source_before == inventory(
        source / "world", world_name="world", path_policy="linux-server"
    )
    with pytest.raises(ValueError, match="fresh target"):
        worker.execute({**request, "action": "apply"}, storage, target, source)


def test_requires_latest_verified_backup_of_current_world(data):
    request, storage, target, source = data
    (source / "world/level.dat").write_bytes(b"not-backed-up")
    with pytest.raises(ValueError, match="fresh verified"):
        worker.plan(request, storage, target, source)
    assert not (target / worker.PLAN).exists()


@pytest.mark.parametrize(
    "change", ["source", "runtime", "settings", "archive", "foreign", "existing"]
)
def test_changed_input_is_refused_before_first_target_write(data, change):
    request, storage, target, source = planned(data)
    if change == "source":
        (source / worker.policy.RANKS).write_bytes(b"changed-ranks")
    elif change == "runtime":
        (target / "server.jar").write_bytes(b"changed-jar")
    elif change == "settings":
        request["world_max_bytes"] = 1
    elif change == "archive":
        request["snapshot"] = "snapshot-" + "0" * 32
    elif change == "foreign":
        (storage / "incoming.zip").write_bytes(b"unfinished")
    else:
        (target / "world").mkdir()
    with pytest.raises((ValueError, OSError)):
        worker.apply(request, storage, target, source)
    assert not (target / worker.PLAN).exists()


@pytest.mark.parametrize(
    "change", ["runtime", "properties", "rank", "receipt", "world", "current"]
)
def test_full_verify_rejects_post_stage_changes(data, change):
    request, storage, target, source = planned(data)
    worker.apply(request, storage, target, source)
    paths = {
        "runtime": target / "server.jar",
        "properties": target / "server.properties",
        "rank": target / worker.policy.RANKS,
        "receipt": target / worker.DONE,
        "world": target / "world/player-progress.dat",
        "current": source / worker.policy.RANKS,
    }
    paths[change].write_bytes(b"changed")
    with pytest.raises(ValueError):
        worker.verify(request, storage, target, source)


def test_interrupted_data_stage_never_creates_owner_receipt(data, monkeypatch):
    request, storage, target, source = planned(data)
    original = worker.policy.execute

    def fail(*_):
        raise OSError("fixture interruption")

    monkeypatch.setattr(worker.policy, "execute", fail)
    with pytest.raises(OSError):
        worker.apply(request, storage, target, source)
    assert (target / worker.PLAN).exists() and not (target / worker.DONE).exists()
    monkeypatch.setattr(worker.policy, "execute", original)
    with pytest.raises(ValueError):
        worker.verify(request, storage, target, source)


def test_budget_refusal_does_not_initialize_target(data, monkeypatch):
    request, storage, target, source = data
    from types import SimpleNamespace  # noqa: PLC0415

    monkeypatch.setattr(worker.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    with pytest.raises(OSError, match="budget"):
        worker.plan(request, storage, target, source)
    assert not (target / worker.PLAN).exists()


@pytest.fixture
def controller(tmp_path, monkeypatch):
    cfg, _ = config(tmp_path)
    source = {"world": "world"}
    target = {"data_volume": "replacement"}
    checkpoint = {"id": "original"}
    state = {
        "checkpoint": checkpoint,
        "destination": {"id": "fresh"},
        "called": [],
        "complete": False,
    }
    monkeypatch.setattr(backups, "target_for", lambda *_: source)
    monkeypatch.setattr(owner, "target_for", lambda *_: target)
    monkeypatch.setattr(backups, "local_engine", lambda: None)
    monkeypatch.setattr(
        backups, "checkpoint", lambda *_: copy.deepcopy(state["checkpoint"])
    )
    monkeypatch.setattr(owner, "destination", lambda *_: dict(state["destination"]))

    def invoke(record, action):
        state["called"].append(action)
        if action == "plan":
            return {"fixture": "plan-hashes-only"}
        if action == "apply":
            state["complete"] = True
            return {"staged": True, "promoted": False}
        if not state["complete"]:
            raise AdminError("Incomplete fixture")
        return {"staged": True, "promoted": False}

    monkeypatch.setattr(owner, "worker", invoke)
    return cfg, state, invoke


def test_owner_lifecycle_and_acknowledgement_recovery(controller, monkeypatch):
    cfg, state, original = controller
    record = owner.plan(cfg, "dj2", "snapshot-" + "a" * 32)

    def lost(record, action):
        result = original(record, action)
        if action == "apply":
            raise OSError("Lost controller response fixture")
        return result

    monkeypatch.setattr(owner, "worker", lost)
    with pytest.raises(AdminError, match="incomplete"):
        owner.run(cfg, record["operation"])
    assert owner.read_record(cfg, record["operation"])["stage"] == "incomplete"
    with pytest.raises(AdminError, match="attempted"):
        owner.run(cfg, record["operation"])
    assert owner.run(cfg, record["operation"], verify=True)["stage"] == "staged"
    assert state["called"] == ["plan", "apply", "verify"]


@pytest.mark.parametrize("change", ["restart", "volume", "ttl", "environment"])
def test_owner_refuses_stale_plan_before_apply(controller, change):
    cfg, state, _ = controller
    record = owner.plan(cfg, "dj2", "snapshot-" + "a" * 32)
    environment = None
    if change == "restart":
        state["checkpoint"] = {"id": "restarted"}
    elif change == "volume":
        state["destination"] = {"id": "replaced"}
    elif change == "ttl":
        record["created_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        owner.save(cfg, record, "planned")
    else:
        environment = {"OMK_BACKUP_MAX_COUNT": "13"}
    with pytest.raises(AdminError):
        owner.run(cfg, record["operation"], environment=environment)
    assert state["called"] == ["plan"]


def test_status_refuses_foreign_credentials(controller):
    cfg, _, _ = controller
    path = owner.journal(cfg, "a" * 32)
    owner._write_private(path, cfg.private, {"api_token": "secret-fixture"})
    with pytest.raises(AdminError, match="journal"):
        owner.read_record(cfg, "a" * 32)


def test_large_non_ftb_entry_limit_is_explicit_and_does_not_allocate_payload():
    from omk.recovery_full_lab import _entries  # noqa: PLC0415

    class Archive:
        def infolist(self):
            files = [
                zipfile.ZipInfo("world/level.dat"),
                zipfile.ZipInfo("world/region/r.0.0.mca"),
            ]
            files[1].file_size = 600 * 1024**2
            return files

        def namelist(self):
            return [p.filename for p in self.infolist()]

    with pytest.raises(ValueError):
        _entries(Archive(), world_name="world")
    assert (
        _entries(Archive(), world_name="world", max_expanded_bytes=1024**3)[1]
        == 600 * 1024**2
    )
