"""Test dependencies for owner restores."""

import copy
import json
import zipfile

import pytest

from omk.backups.backup_store import BackupStore
from omk.backups.stopped_world_backup import inventory
from omk.owner import (
    admin_backups as backups,
    admin_restores as owner,
)
from omk.owner.admin import AdminError
from omk.worlds import owner_restore_worker as worker
from tests.fixtures.unit.owner.operator_commands import config
from tests.fixtures.unit.worlds.linux_restore_policy import LIMITS, build


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


def write_targets(cfg, filename, entries):
    text = "schema=1\n"
    for name, value in entries.items():
        text += (
            "[servers."
            + name
            + "]\n"
            + "\n".join(k + "=" + json.dumps(v) for k, v in value.items())
            + "\n"
        )
    path = cfg.private / filename
    path.write_text(text)
    path.chmod(0o600)


@pytest.fixture
def targets(tmp_path):
    cfg, _ = config(tmp_path)
    source = {
        "container": "source",
        "data_volume": "source-data",
        "store_volume": "source-store",
        "label": "omkality.test",
        "source_owner": "source-owner",
        "store_owner": "store-owner",
        "world": "world",
        "image": backups.IMAGE,
        "release": "fixture-v1",
    }
    dest = {
        "data_volume": "replacement",
        "label": "omkality.test",
        "owner": "replacement-owner",
        "image": backups.IMAGE,
        "release": "fixture-v1",
    }
    write_targets(cfg, "backups.toml", {"dj2": source})
    write_targets(cfg, "restores.toml", {"dj2": dest})
    return cfg, source, dest
