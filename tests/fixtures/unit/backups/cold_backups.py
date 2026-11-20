"""Test dependencies for cold backups."""

import pytest

from omk.backups import cold_backup_worker as worker
from omk.backups.stopped_world_backup import LAB_POLICY
from omk.owner import admin_backups as owner
from tests.fixtures.unit.owner.operator_commands import config


@pytest.fixture
def fixture(tmp_path):
    root, storage = tmp_path / "server", tmp_path / "backups"
    (root / "world" / "data").mkdir(parents=True)
    (root / "world/level.dat").write_bytes(b"level-fixture")
    (root / "world/data/teams.dat").write_bytes(b"ftb-fixture")
    (root / "server.properties").write_bytes(b"test-config")
    (root / "server.jar").write_bytes(b"jar-fixture")
    storage.mkdir()
    request = {
        "operation": "a" * 32,
        "world": "world",
        "world_max_bytes": 1024**2,
        "policy": vars(LAB_POLICY),
    }
    request.update(worker.execute({**request, "action": "plan"}, root, storage))
    return root, storage, request


def stopped():
    return {
        "Id": "container-id",
        "Image": "sha256:" + "a" * 64,
        "Created": "created",
        "RestartCount": 0,
        "Config": {
            "Labels": {"omkality.test": "source-owner"},
            "Image": "java@sha256:" + "a" * 64,
        },
        "State": {
            "Status": "exited",
            "Running": False,
            "OOMKilled": False,
            "ExitCode": 0,
            "StartedAt": "start",
            "FinishedAt": "finish",
        },
        "HostConfig": {
            "RestartPolicy": {"Name": "no"},
            "LogConfig": {
                "Type": "local",
                "Config": {"max-size": "10m", "max-file": "3"},
            },
        },
        "Mounts": [{"Name": "source-volume", "Type": "volume", "Destination": "/srv"}],
    }


def controller(fixture, tmp_path, monkeypatch):
    root, storage, _ = fixture
    cfg, path = config(tmp_path)
    target = {"world": "world"}
    state = {"store": {}, "id": "same-container"}
    monkeypatch.setattr(owner, "target_for", lambda *a: dict(target))
    monkeypatch.setattr(owner, "local_engine", lambda: None)
    monkeypatch.setattr(owner, "volume", lambda *a: {})
    monkeypatch.setattr(owner, "checkpoint", lambda *a: dict(state))
    monkeypatch.setattr(owner, "worker", lambda t, r: worker.execute(r, root, storage))
    actual_settings = owner.settings
    fixture_env = {
        "OMK_BACKUP_MAX_BYTES": str(128 * 1024**2),
        "OMK_BACKUP_STAGING_BYTES": str(64 * 1024**2),
        "OMK_BACKUP_RESERVE_BYTES": str(16 * 1024**2),
        "OMK_BACKUP_WORLD_MAX_BYTES": str(1024**2),
        "OMK_BACKUP_MAX_COUNT": "4",
    }
    monkeypatch.setattr(
        owner,
        "settings",
        lambda environment=None: actual_settings(
            {**fixture_env, **(environment or {})}
        ),
    )
    return cfg, path, root, storage, target
