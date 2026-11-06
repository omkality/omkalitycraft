import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from omk import stopped_world_backup as backup
from omk.backup_archive import verify_archive
from omk.backup_store import BackupStore
from omk.managed_world_backup_lab import ManagedWorldBackups
from omk.recovery_lab import _validate_inputs


@pytest.fixture
def fixture(tmp_path):
    world = tmp_path / "lab-world"
    world.mkdir()
    for name, data in {
        "level.dat": b"level fixture",
        "playerdata/player.dat": b"inventory",
        "DIM-1/region/r.0.0.mca": b"nether",
        "data/ftb_lib/teams/team.dat": b"claims",
    }.items():
        path = world / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    storage = tmp_path / "backups"
    storage.mkdir()
    return world, storage, replace(backup.LAB_POLICY, max_count=2)


def test_snapshot_independent_inventory_covers_player_ftb_and_other_dimensions(fixture):
    world, storage, policy = fixture
    before = backup.inventory(world)
    result = backup.snapshot(world, storage, policy)
    root = storage / "store" / result["id"]
    assert result["verified"] and result["inventory_files"] == 4
    assert verify_archive(root / "archive.zip", before) == result["sha256"]
    assert json.loads((root / "manifest.json").read_bytes())["files"] == before
    assert backup.inventory(world) == before
    assert not (storage / "incoming.zip").exists()


def test_real_archive_quota_refusal_preserves_history_before_retention(fixture):
    world, storage, policy = fixture
    backup.snapshot(world, storage, policy)
    (world / "level.dat").write_bytes(b"second checkpoint")
    backup.snapshot(world, storage, policy)
    result = backup.fault_and_retention(world, storage, policy)
    assert result["quota_refused_without_history_change"]
    assert result["new_verified_before_retirement"]
    assert [r["sequence"] for r in result["history"]] == [2, 3]


@pytest.mark.parametrize(
    "failure", ["changed-source", "space", "staging-limit", "interrupted"]
)
def test_failure_never_changes_previous_verified_copy(fixture, monkeypatch, failure):
    world, storage, policy = fixture
    first = backup.snapshot(world, storage, policy)
    store = BackupStore(storage / "store", policy)
    before = store.inspect()
    if failure == "changed-source":
        real = backup.inventory

        def changing(path, **kwargs):
            value = real(path, **kwargs)
            changing.calls += 1
            if changing.calls > 1:
                value["lab-world/level.dat"]["sha256"] = "a" * 64
            return value

        changing.calls = 0
        monkeypatch.setattr(backup, "inventory", changing)
    elif failure == "space":
        monkeypatch.setattr(
            backup.shutil, "disk_usage", lambda _: SimpleNamespace(free=0)
        )
    elif failure == "staging-limit":
        policy = replace(policy, staging_bytes=1)
    else:
        (storage / "incoming.zip").write_bytes(b"interrupted")
    with pytest.raises((ValueError, OSError)):
        backup.snapshot(world, storage, policy)
    assert store.inspect() == before
    archive = storage / "store" / first["id"] / "archive.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == first["sha256"]


@pytest.mark.parametrize("failure", ["no-level", "link", "case-collision"])
def test_incomplete_or_unsafe_world_does_not_create_store(fixture, failure):
    world, storage, policy = fixture
    if failure == "no-level":
        (world / "level.dat").unlink()
    elif failure == "link":
        try:
            (world / "linked").symlink_to(
                world / "playerdata", target_is_directory=True
            )
        except OSError:
            pytest.skip("Creating links requires platform permission")
    else:
        (world / "Case.dat").write_bytes(b"one")
        other = world / "case.dat"
        if other.exists():
            pytest.skip("Case-insensitive host filesystem")
        other.write_bytes(b"two")
    with pytest.raises(ValueError):
        backup.snapshot(world, storage, policy)
    assert not (storage / "store").exists()


def test_bad_managed_runtime_flags_fail_before_artifact_or_docker_access():
    args = SimpleNamespace(
        managed_backups=True,
        runtime="native",
        full_backup_return=True,
        edge_cases=True,
        rank_policy=True,
        access_policy=True,
    )
    with pytest.raises(ValueError, match="Managed backup lab requires"):
        _validate_inputs(args)


@pytest.mark.parametrize("failure", ["running", "no-checkpoint"])
def test_managed_source_requires_verified_stopped_checkpoint(monkeypatch, failure):
    adapter = object.__new__(ManagedWorldBackups)
    recovery = SimpleNamespace(
        server=SimpleNamespace(
            process=SimpleNamespace(poll=lambda: None if failure == "running" else 0)
        ),
        checkpoint_export=None if failure == "no-checkpoint" else ("path", "digest"),
    )
    monkeypatch.setattr(
        "omk.managed_world_backup_lab.docker",
        lambda *a, **k: pytest.fail("Docker touched"),
    )
    with pytest.raises(ValueError, match="verified stopped"):
        adapter.verify_source(recovery)


def test_export_missing_volume_refuses_before_docker_can_create_it(
    tmp_path, monkeypatch
):
    adapter = object.__new__(ManagedWorldBackups)
    adapter.volume, adapter.run = "owned-backup", "fixture-run"
    monkeypatch.setattr("omk.managed_world_backup_lab.inspect_owned", lambda *a: None)
    monkeypatch.setattr(
        "omk.managed_world_backup_lab.docker",
        lambda *a, **k: pytest.fail("Docker mount attempted"),
    )
    with pytest.raises(ValueError, match="never create"):
        adapter.copy_from_store("store", tmp_path / "new-export")
