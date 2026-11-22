"""Test dependencies for resource reset stage."""

import zipfile
from uuid import uuid4

import pytest

from launcher.nbt import Tag
from omk.backups.backup_store import BackupPolicy, BackupStore
from omk.backups.stopped_world_backup import inventory
from omk.worlds.reset import resource_reset_stage as stage
from tests.fixtures.unit.backups.ftb_restore_authority import records
from tests.fixtures.unit.worlds.resource_reset_inventory import (
    encoded,
    sample,
)

__all__ = ["records", "sample"]


LIMITS = BackupPolicy(32 * 1024**2, 3, 16 * 1024**2, 1)


@pytest.fixture
def data(sample, tmp_path, monkeypatch):
    server, world, entity, player, _records = sample
    (server / "server.properties").write_text("level-name=world\nlevel-seed=\n")
    (world / "DIM-18000/region").mkdir()
    (world / "DIM-18000/region/r.0.0.mca").write_bytes(b"old-resource")
    (world / "region").mkdir()
    (world / "region/r.0.0.mca").write_bytes(b"keep-main-base")
    (world / "betterquesting").mkdir()
    (world / "betterquesting/QuestProgress.json").write_bytes(
        b'{"keep":"quest-progress"}'
    )
    (world / "stats").mkdir()
    (world / "stats" / (player.stem + ".json")).write_bytes(
        b'{"stat.playOneMinute":72007,"stat.jump":9}'
    )
    entity["ForgeData"] = Tag(
        10,
        {
            "PlayerPersisted": Tag(
                10,
                {
                    "omkality_guide": Tag(
                        10,
                        {
                            "last_auto": Tag(4, 1794560000),
                            "last_help": Tag(4, 1794560001),
                        },
                    )
                },
            )
        },
    )
    encoded(player, entity)
    encoded(player.with_suffix(".dat_old"), entity)
    storage, target = tmp_path / "backup", tmp_path / "candidate"
    storage.mkdir()
    target.mkdir()
    store = BackupStore.create(storage / "store", LIMITS, path_policy="linux-server")
    files = inventory(world, world_name="world", path_policy="linux-server")
    archive = tmp_path / "fresh.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        for name in files:
            out.write(server / name, name)
    snapshot = store.publish(archive, files)
    request = {
        "schema": 1,
        "operation": uuid4().hex,
        "world": "world",
        "dimension": -18000,
        "position": [8, 100, 8],
        "snapshot": snapshot["id"],
        "world_max_bytes": 8 * 1024**2,
        "policy": vars(LIMITS),
    }
    monkeypatch.setattr(stage.sys, "platform", "linux")
    return request, server, storage, target, files
